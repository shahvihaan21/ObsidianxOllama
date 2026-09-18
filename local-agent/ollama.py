"""Minimal Ollama client built on the standard library (urllib + json only).

No SDK, no requests, no provider abstraction. Public surface:

    Ollama.is_available()          -> bool
    Ollama.list_models()           -> list[str]
    Ollama.has_model()             -> bool
    Ollama.chat(messages, tools=)  -> ChatResponse
    Ollama.chat_stream(messages)   -> Iterator[str]

Every failure is a controlled OllamaError subclass, so the assistant can report
"Ollama is not running. Start Ollama and try again." instead of a traceback.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterator

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:1.7b"
NOT_RUNNING_MESSAGE = "Ollama is not running. Start Ollama and try again."


class OllamaError(RuntimeError):
    """Base class for every Ollama failure."""


class OllamaUnavailable(OllamaError):
    """The server could not be reached."""

    def __init__(self, host: str = "", detail: str = "") -> None:
        self.host = host
        self.detail = detail
        message = NOT_RUNNING_MESSAGE
        if host:
            message += f" (tried {host}"
            message += f": {detail})" if detail else ")"
        super().__init__(message)


class ModelNotFound(OllamaError):
    """The configured model is not installed locally."""

    def __init__(self, model: str, available: list[str] | None = None) -> None:
        self.model = model
        self.available = list(available or [])
        super().__init__(
            f"Model {model!r} is not installed in Ollama. Run: ollama pull {model}"
        )


class OllamaHTTPError(OllamaError):
    """The server answered with a non-2xx status."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"Ollama returned HTTP {status}: {body[:300]}")


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ToolCall":
        function = raw.get("function") or {}
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                arguments = {"_raw": arguments}
        if not isinstance(arguments, dict):
            arguments = {}
        return cls(name=str(function.get("name") or ""), arguments=arguments)

    def to_api(self) -> dict[str, Any]:
        return {"function": {"name": self.name, "arguments": self.arguments}}


@dataclass
class ChatMessage:
    """One conversation turn."""

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: str = ""

    @classmethod
    def user(cls, text: str) -> "ChatMessage":
        return cls(role="user", content=text)

    @classmethod
    def system(cls, text: str) -> "ChatMessage":
        return cls(role="system", content=text)

    @classmethod
    def assistant(cls, text: str = "") -> "ChatMessage":
        return cls(role="assistant", content=text)

    @classmethod
    def tool_result(cls, name: str, text: str) -> "ChatMessage":
        return cls(role="tool", content=text, tool_name=name)

    def to_api(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [call.to_api() for call in self.tool_calls]
        if self.role == "tool" and self.tool_name:
            message["tool_name"] = self.tool_name
        return message


@dataclass
class ChatResponse:
    """Result of a chat call."""

    message: ChatMessage
    model: str = ""
    done_reason: str = ""
    eval_count: int = 0
    prompt_eval_count: int = 0


def as_message(message: Any) -> ChatMessage:
    """Accept a ChatMessage or a plain ``{"role": ..., "content": ...}`` dict."""
    if isinstance(message, ChatMessage):
        return message
    if isinstance(message, dict):
        return ChatMessage(
            role=str(message.get("role") or "user"),
            content=str(message.get("content") or ""),
            tool_name=str(message.get("tool_name") or ""),
        )
    raise TypeError(f"Unsupported message type: {type(message)!r}")


class Ollama:
    """Small, dependency-free Ollama client."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        temperature: float = 0.3,
        num_ctx: int = 4096,
        keep_alive: str = "5m",
    ) -> None:
        self.host = (host or DEFAULT_HOST).rstrip("/")
        self.model = model or DEFAULT_MODEL
        self.timeout = float(timeout)
        self.temperature = float(temperature)
        self.num_ctx = int(num_ctx)
        self.keep_alive = keep_alive

    # -- low-level HTTP -------------------------------------------------

    def _request(
        self, path: str, payload: dict[str, Any] | None = None, method: str = "POST"
    ):
        url = f"{self.host}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise OllamaHTTPError(exc.code, body) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise OllamaUnavailable(self.host, str(getattr(exc, "reason", exc))) from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        with self._request(path, method="GET") as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._request(path, payload) as response:
            return json.loads(response.read().decode("utf-8"))

    # -- health ---------------------------------------------------------

    def is_available(self) -> bool:
        """True when the Ollama server answers."""
        try:
            self._get_json("/api/tags")
            return True
        except OllamaError:
            return False

    def list_models(self) -> list[str]:
        """Names of installed models, or [] when the server is unreachable."""
        try:
            data = self._get_json("/api/tags")
        except OllamaError:
            return []
        return [str(model.get("name") or "") for model in data.get("models") or []]

    def has_model(self, model: str | None = None) -> bool:
        """True when *model* (default: the configured one) is installed."""
        target = model or self.model
        names = self.list_models()
        if target in names:
            return True
        base = target.split(":")[0]
        return any(name.split(":")[0] == base for name in names)

    def check(self) -> str:
        """Return "" when ready to chat, otherwise a user-facing message."""
        if not self.is_available():
            return NOT_RUNNING_MESSAGE
        if not self.list_models():
            return f"Ollama has no models installed. Run: ollama pull {self.model}"
        if not self.has_model():
            return f"Model {self.model!r} is not installed. Run: ollama pull {self.model}"
        return ""

    # -- chat -----------------------------------------------------------

    def _payload(
        self, messages, tools: list[dict[str, Any]] | None = None, stream: bool = False
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [as_message(message).to_api() for message in messages],
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = tools
        return payload

    def chat(
        self, messages, tools: list[dict[str, Any]] | None = None
    ) -> ChatResponse:
        """Blocking chat completion. Raises OllamaUnavailable when offline."""
        data = self._post_json("/api/chat", self._payload(messages, tools))
        raw = data.get("message") or {}
        message = ChatMessage(
            role=str(raw.get("role") or "assistant"),
            content=str(raw.get("content") or ""),
            tool_calls=[ToolCall.from_api(call) for call in raw.get("tool_calls") or []],
        )
        return ChatResponse(
            message=message,
            model=str(data.get("model") or self.model),
            done_reason=str(data.get("done_reason") or ""),
            eval_count=int(data.get("eval_count") or 0),
            prompt_eval_count=int(data.get("prompt_eval_count") or 0),
        )

    def chat_stream(
        self, messages, tools: list[dict[str, Any]] | None = None
    ) -> Iterator[str]:
        """Yield response text as it arrives (newline-delimited JSON)."""
        payload = self._payload(messages, tools, stream=True)
        with self._request("/api/chat", payload) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise OllamaHTTPError(200, str(chunk["error"]))
                piece = (chunk.get("message") or {}).get("content") or ""
                if piece:
                    yield piece
                if chunk.get("done"):
                    break
