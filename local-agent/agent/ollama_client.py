"""Native Ollama HTTP client.

Uses only the Python standard library (``urllib``) plus a background thread for
reading streamed responses. No ``requests``, no SDK, no vendor package -- this
keeps the dependency surface tiny on an 8 GB machine and means the client works
even before venv packages are installed.

Responsibilities:
  * connectivity + model availability checks with actionable error messages
  * blocking and streaming chat
  * native tool-call passthrough (Ollama's ``tools`` field)
  * timeouts, bounded retries, structured errors
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Sequence

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class OllamaError(RuntimeError):
    """Base class for all Ollama client failures."""


class OllamaUnavailable(OllamaError):
    """The Ollama server could not be reached."""

    def __init__(self, host: str, detail: str = "") -> None:
        self.host = host
        self.detail = detail
        msg = (
            f"Cannot reach Ollama at {host}.\n"
            f"  detail: {detail or 'connection refused'}\n"
            "  fix:    start Ollama (run `ollama serve`, or launch the Ollama app),\n"
            "          then re-run diagnostics.bat"
        )
        super().__init__(msg)


class ModelNotFound(OllamaError):
    """The configured model is not installed locally."""

    def __init__(self, model: str, available: Sequence[str] = ()) -> None:
        self.model = model
        self.available = list(available)
        listing = "\n".join(f"    - {m}" for m in self.available) or "    (none installed)"
        msg = (
            f"Model {model!r} is not installed in Ollama.\n"
            f"  installed models:\n{listing}\n"
            f"  fix:    ollama pull {model}\n"
            f"  or change the model in config/config.json -> ollama.model"
        )
        super().__init__(msg)


class OllamaHTTPError(OllamaError):
    """The server returned a non-2xx status."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"Ollama returned HTTP {status}: {body[:400]}")


# --------------------------------------------------------------------------
# Data types
# --------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ToolCall":
        fn = raw.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            # Some models emit arguments as a JSON string rather than an object.
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {}
        return cls(name=str(fn.get("name") or ""), arguments=args, id=str(raw.get("id") or ""))

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass
class ChatMessage:
    """One conversation turn."""

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: str = ""
    thinking: str = ""

    @classmethod
    def user(cls, text: str) -> "ChatMessage":
        return cls(role="user", content=text)

    @classmethod
    def system(cls, text: str) -> "ChatMessage":
        return cls(role="system", content=text)

    @classmethod
    def assistant(cls, text: str = "", tool_calls: list[ToolCall] | None = None) -> "ChatMessage":
        return cls(role="assistant", content=text, tool_calls=tool_calls or [])

    @classmethod
    def tool_result(cls, name: str, content: str) -> "ChatMessage":
        return cls(role="tool", content=content, tool_name=name)

    def to_api(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [tc.to_api() for tc in self.tool_calls]
        if self.role == "tool" and self.tool_name:
            msg["tool_name"] = self.tool_name
        return msg


@dataclass
class ChatResponse:
    """Result of a non-streaming chat call."""

    message: ChatMessage
    model: str = ""
    done_reason: str = ""
    eval_count: int = 0
    prompt_eval_count: int = 0
    total_duration_ns: int = 0
    load_duration_ns: int = 0

    @property
    def tokens_per_second(self) -> float:
        if not self.eval_count or not self.total_duration_ns:
            return 0.0
        return self.eval_count / (self.total_duration_ns / 1e9)


@dataclass
class ModelInfo:
    """A locally installed Ollama model."""

    name: str
    size: int = 0
    parameter_size: str = ""
    quantization: str = ""
    capabilities: list[str] = field(default_factory=list)

    def has(self, capability: str) -> bool:
        return capability.lower() in {c.lower() for c in self.capabilities}

    def __str__(self) -> str:
        caps = ",".join(self.capabilities) or "?"
        return f"{self.name} ({self.parameter_size or '?'}, {caps})"


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class OllamaClient:
    """Minimal, dependency-free Ollama client."""

    def __init__(
        self,
        host: str = "http://127.0.0.1:11434",
        model: str = "qwen3:1.7b",
        timeout: int = 300,
        max_retries: int = 2,
        num_ctx: int = 4096,
        keep_alive: str = "5m",
        think: bool = False,
        temperature: float = 0.3,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.think = think
        self.temperature = temperature
        self._cancel = threading.Event()

    # -- cancellation ------------------------------------------------------

    def cancel(self) -> None:
        """Request cancellation of an in-flight streaming call."""
        self._cancel.set()

    def reset_cancel(self) -> None:
        self._cancel.clear()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # -- low level ---------------------------------------------------------

    def _request(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        method: str = "POST",
        stream: bool = False,
    ):
        url = f"{self.host}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        # Streaming responses must not be buffered until EOF.
        timeout = None if stream else self.timeout
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise OllamaHTTPError(exc.code, body) from exc
        except urllib.error.URLError as exc:
            raise OllamaUnavailable(self.host, str(exc.reason)) from exc
        except OSError as exc:
            raise OllamaUnavailable(self.host, str(exc)) from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        with self._request(path, method="GET") as resp:
            return json.loads(resp.read().decode("utf-8"))

    # -- health ------------------------------------------------------------

    def is_available(self) -> bool:
        """True when the Ollama server answers."""
        try:
            self._get_json("/api/tags")
            return True
        except OllamaError:
            return False

    def list_models(self) -> list[ModelInfo]:
        """Return installed models, or [] when the server is unreachable."""
        try:
            data = self._get_json("/api/tags")
        except OllamaError:
            return []
        out: list[ModelInfo] = []
        for m in data.get("models", []):
            details = m.get("details") or {}
            out.append(
                ModelInfo(
                    name=m.get("name", ""),
                    size=int(m.get("size") or 0),
                    parameter_size=details.get("parameter_size", ""),
                    quantization=details.get("quantization_level", ""),
                    capabilities=list(m.get("capabilities") or []),
                )
            )
        return out

    def model_names(self) -> list[str]:
        return [m.name for m in self.list_models()]

    def has_model(self, model: str | None = None) -> bool:
        """True when ``model`` (default: configured) is installed.

        Accepts a bare name for a tagged model, so ``qwen3`` matches
        ``qwen3:1.7b``.
        """
        target = model or self.model
        names = self.model_names()
        if target in names:
            return True
        base = target.split(":")[0]
        return any(n.split(":")[0] == base for n in names)

    def ensure_ready(self, model: str | None = None) -> None:
        """Raise a precise, actionable error if we cannot chat right now."""
        target = model or self.model
        try:
            names = self.model_names()
        except OllamaUnavailable:
            raise
        except OllamaError as exc:
            raise OllamaUnavailable(self.host, str(exc)) from exc
        if not names:
            raise OllamaUnavailable(
                self.host, "server responded but reported zero installed models"
            )
        if not self.has_model(target):
            raise ModelNotFound(target, names)

    def model_info(self, model: str | None = None) -> dict[str, Any]:
        """Return raw ``/api/show`` data for a model."""
        return self._post_json("/api/show", {"model": model or self.model})

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._request(path, payload) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def supports_tools(self, model: str | None = None) -> bool:
        """True when the model advertises native tool calling."""
        target = model or self.model
        for m in self.list_models():
            if m.name == target or m.name.split(":")[0] == target.split(":")[0]:
                return m.has("tools")
        return False

    # -- chat --------------------------------------------------------------

    def _build_payload(
        self,
        messages: Sequence[ChatMessage],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_api() for m in messages],
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = tools
        # `think` is only sent when disabling it; older servers reject unknown fields.
        if self.think is False:
            payload["think"] = False
        return payload

    def chat(
        self,
        messages: Sequence[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> ChatResponse:
        """Blocking chat completion with retries on transient failure."""
        temp = self.temperature if temperature is None else temperature
        payload = self._build_payload(messages, tools, temp, stream=False)
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                data = self._post_json("/api/chat", payload)
                return self._parse_response(data)
            except OllamaHTTPError:
                raise  # a 4xx/5xx will not fix itself by retrying
            except OllamaError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait = 1.0 * (attempt + 1)
                    log.warning(
                        "Ollama chat failed (attempt %d/%d): %s -- retrying in %.0fs",
                        attempt + 1, self.max_retries + 1, exc, wait,
                    )
                    time.sleep(wait)

        assert last_exc is not None
        raise last_exc

    def _parse_response(self, data: dict[str, Any]) -> ChatResponse:
        raw_msg = data.get("message") or {}
        tool_calls = [ToolCall.from_api(tc) for tc in (raw_msg.get("tool_calls") or [])]
        message = ChatMessage(
            role=raw_msg.get("role", "assistant"),
            content=raw_msg.get("content") or "",
            tool_calls=tool_calls,
            thinking=raw_msg.get("thinking") or "",
        )
        return ChatResponse(
            message=message,
            model=data.get("model", self.model),
            done_reason=data.get("done_reason", "") or "",
            eval_count=int(data.get("eval_count") or 0),
            prompt_eval_count=int(data.get("prompt_eval_count") or 0),
            total_duration_ns=int(data.get("total_duration") or 0),
            load_duration_ns=int(data.get("load_duration") or 0),
        )

    def chat_stream(
        self,
        messages: Sequence[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> ChatResponse:
        """Streaming chat.

        Tokens are pushed to ``on_token`` as they arrive (for TTS / display), and
        the fully assembled response is returned. Honours :meth:`cancel`, which
        stops reading and returns whatever text was produced so far.
        """
        temp = self.temperature if temperature is None else temperature
        payload = self._build_payload(messages, tools, temp, stream=True)
        self.reset_cancel()

        content_parts: list[str] = []
        thinking_parts: list[str] = []
        collected_calls: list[ToolCall] = []
        last: dict[str, Any] = {}

        try:
            resp = self._request("/api/chat", payload, stream=True)
        except OllamaError:
            raise

        try:
            for raw_line in resp:
                if self.cancelled:
                    log.info("stream cancelled by caller")
                    break
                line = raw_line.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                last = chunk
                if chunk.get("error"):
                    raise OllamaHTTPError(200, str(chunk["error"]))
                msg = chunk.get("message") or {}
                piece = msg.get("content") or ""
                if piece:
                    content_parts.append(piece)
                    if on_token:
                        try:
                            on_token(piece)
                        except Exception:  # a bad callback must not kill the stream
                            log.exception("on_token callback raised")
                if msg.get("thinking"):
                    thinking_parts.append(msg["thinking"])
                for tc in msg.get("tool_calls") or []:
                    call = ToolCall.from_api(tc)
                    # Streamed tool calls arrive once, fully formed.
                    if not any(c.name == call.name and c.arguments == call.arguments
                               for c in collected_calls):
                        collected_calls.append(call)
                if chunk.get("done"):
                    break
        finally:
            resp.close()

        message = ChatMessage(
            role="assistant",
            content="".join(content_parts),
            tool_calls=collected_calls,
            thinking="".join(thinking_parts),
        )
        return ChatResponse(
            message=message,
            model=last.get("model", self.model),
            done_reason=last.get("done_reason", "") or "",
            eval_count=int(last.get("eval_count") or 0),
            prompt_eval_count=int(last.get("prompt_eval_count") or 0),
            total_duration_ns=int(last.get("total_duration") or 0),
            load_duration_ns=int(last.get("load_duration") or 0),
        )

    # -- maintenance -------------------------------------------------------

    def preload(self) -> float:
        """Load the model into memory. Returns seconds taken."""
        started = time.time()
        try:
            self._post_json("/api/generate", {"model": self.model, "prompt": "", "keep_alive": self.keep_alive})
        except OllamaError as exc:
            raise OllamaError(f"Failed to preload model {self.model!r}: {exc}") from exc
        return time.time() - started

    def unload(self) -> None:
        """Ask Ollama to evict the model from RAM (frees ~1-2 GB)."""
        try:
            self._post_json("/api/generate", {"model": self.model, "keep_alive": 0})
        except OllamaError as exc:
            log.warning("Could not unload model: %s", exc)

    def loaded_models(self) -> list[dict[str, Any]]:
        """Models currently resident in RAM via ``/api/ps``."""
        try:
            return self._get_json("/api/ps").get("models", [])
        except OllamaError:
            return []

    def version(self) -> str:
        try:
            return self._get_json("/api/version").get("version", "unknown")
        except OllamaError:
            return "unavailable"


def iter_stream_text(chunks: Iterator[str]) -> str:
    """Join an iterator of text chunks. Small helper used by tests."""
    return "".join(chunks)
