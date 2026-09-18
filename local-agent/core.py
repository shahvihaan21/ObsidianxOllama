"""Command router and conversation controller.

Deterministic first: obvious commands are recognised with a handful of small
regex patterns and dispatched straight to a tool. Everything else goes to
Ollama. There is no agent loop, no manager, no event bus -- just:

    input -> routing -> tool or Ollama -> response
"""

from __future__ import annotations

import re

from obsidian import NOTE_NOT_FOUND, ObsidianError
from ollama import ModelNotFound, OllamaError, OllamaUnavailable

OLLAMA_NOT_RUNNING = "Ollama is not running. Start Ollama and try again."
CANCELLED = "Okay, cancelled."
NO_ANSWER = "I don't have an answer for that."
NO_NOTE = "Which note do you mean?"
MAX_HISTORY_MESSAGES = 12

DEFAULT_SYSTEM_PROMPT = (
    "You are a concise, practical assistant running locally on the user's "
    "Windows laptop. Answer in plain text, lead with the answer, and keep it "
    "short unless the user asks for detail."
)

_YES_WORDS = {
    "y", "yes", "yeah", "yep", "yup", "sure", "ok", "okay",
    "confirm", "confirmed", "go", "go ahead", "do it", "proceed",
}

# -- routing patterns ------------------------------------------------------
# Order matters: notes are checked before web search, so "search my notes for X"
# is not mistaken for a Google search.

_OBS_CREATE = re.compile(
    r"^\s*(?:please\s+)?(?:create|make|add|start|new)\s+"
    r"(?:me\s+)?(?:a\s+|an\s+)?(?:new\s+)?(?:obsidian\s+)?notes?\b"
    r"(?:\s+(?:called|named|titled|for|about))?\s*[:,-]?\s*"
    r"(?P<note>[^:]+?)"
    r"(?:\s*(?::|with\s+(?:the\s+)?(?:content|text)s?\s*|containing\s*)"
    r"\s*(?P<content>.*?))?\s*$",
    re.IGNORECASE,
)

_OBS_APPEND_NAME_FIRST = re.compile(
    r"^\s*(?:please\s+)?append\s+(?:this\s+|the\s+following\s+)?(?:to\s+)?"
    r"(?:my\s+|the\s+|your\s+)?(?:obsidian\s+)?(?P<note>.+?)\s+note\b"
    r"\s*[:,-]?\s*(?P<content>.*)$",
    re.IGNORECASE,
)

_OBS_APPEND_KEYWORD = re.compile(
    r"^\s*(?:please\s+)?append\s+(?:this\s+|the\s+following\s+)?(?:to\s+)?"
    r"(?:my\s+|the\s+|your\s+)?(?:obsidian\s+)?note\s+"
    r"(?:called|named|titled)\s+(?P<note>.+?)"
    r"\s*[:,-]\s*(?P<content>.+)$",
    re.IGNORECASE,
)

_OBS_SEARCH = re.compile(
    r"^\s*(?:please\s+)?(?:search|find|look\s+up|show)\s+"
    r"(?:for\s+|in\s+|through\s+|inside\s+)?"
    r"(?:my\s+|the\s+|your\s+)?(?:obsidian\s+)?(?:notes?|vault|memory)\b"
    r"(?:\s+(?:for|about|on|containing|mentioning|with|related\s+to)\s+"
    r"(?P<q>.+?))?\s*[?.!]*$",
    re.IGNORECASE,
)

_OBS_READ = re.compile(
    r"^\s*(?:please\s+)?(?:read|open|show|get|fetch|display)\s+(?:me\s+)?"
    r"(?:my\s+|the\s+|your\s+)?(?:obsidian\s+)?(?:note|notes|file)\b"
    r"(?:\s+(?:called|named|titled|about))?\s*[:,-]?\s*"
    r"(?P<note>.+?)\s*[?.!]*$",
    re.IGNORECASE,
)

_GOOGLE = re.compile(
    r"^\s*(?:please\s+)?(?:search|google|look\s+up)\s+"
    r"(?:(?:for|about)\s+)?"
    r"(?:(?:on\s+)?(?:the\s+)?(?:google|web|internet|online)\s+)?"
    r"(?:(?:for|about)\s+)?"
    r"(?P<q>\S.*?)\s*[?.!]*$",
    re.IGNORECASE,
)

_OPEN_APP = re.compile(
    r"^\s*(?:please\s+)?(?:open|launch|start|run)\s+(?:up\s+)?"
    r"(?:the\s+|my\s+|a\s+)?(?:app\s+|application\s+|program\s+)?"
    r"(?P<app>[A-Za-z0-9 ._+'\-]{1,40}?)"
    r"(?:\s+(?:app|application|program))?\s*[?.!]*$",
    re.IGNORECASE,
)


def squeeze(text: str) -> str:
    """Collapse whitespace so patterns only ever see single spaces."""
    return " ".join(str(text or "").split())


def parse_yes(answer: object) -> bool:
    """Only an explicit affirmative counts as confirmation."""
    if isinstance(answer, bool):
        return answer
    return str(answer or "").strip().lower().strip(".!") in _YES_WORDS


def default_confirm(question: str) -> bool:
    """Ask on the console. Used when the assistant runs interactively."""
    try:
        return parse_yes(input(f"{question} [y/N] "))
    except (EOFError, KeyboardInterrupt):
        print()
        return False


class Assistant:
    """Routes one request at a time and keeps a small conversation history."""

    def __init__(
        self,
        ollama,
        tools,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        confirm=default_confirm,
        max_history: int = MAX_HISTORY_MESSAGES,
    ) -> None:
        self.ollama = ollama
        self.tools = tools
        self.system_prompt = system_prompt
        self.confirm = confirm
        self.max_history = max(2, int(max_history))
        self.history: list[dict[str, str]] = []

    # -- public API -----------------------------------------------------

    def handle(self, text: str) -> str:
        """Turn one line of user input into one response string."""
        request = squeeze(text)
        if not request:
            return ""
        for route in (
            self._try_create_note,
            self._try_append_note,
            self._try_search_notes,
            self._try_read_note,
            self._try_google,
            self._try_open_app,
        ):
            handled, response = route(request)
            if handled:
                return response
        return self._ask_ollama(request)

    def reset(self) -> None:
        """Forget the conversation (not the notes)."""
        self.history.clear()

    # -- deterministic routes -------------------------------------------

    def _try_create_note(self, request: str) -> tuple[bool, str]:
        match = _OBS_CREATE.match(request)
        if not match:
            return False, ""
        note = match.group("note").strip(" \t\"'")
        if not note:
            return True, "What should the note be called?"
        content = (match.group("content") or "").strip()
        try:
            path = self.tools.obsidian_path(note)
        except ObsidianError as exc:
            return True, str(exc)
        if not self._confirm(f'Create "{path}" in your Obsidian vault?'):
            return True, CANCELLED
        return True, self._call_tool(lambda: self.tools.obsidian_create(note, content))

    def _try_append_note(self, request: str) -> tuple[bool, str]:
        match = _OBS_APPEND_KEYWORD.match(request) or _OBS_APPEND_NAME_FIRST.match(request)
        if not match:
            return False, ""
        note = match.group("note").strip(" \t\"'")
        content = (match.group("content") or "").strip()
        if not note:
            return True, NO_NOTE
        try:
            path = self.tools.obsidian_path(note)
            exists = self.tools.obsidian_exists(note)
        except ObsidianError as exc:
            return True, str(exc)
        if not exists:
            return True, NOTE_NOT_FOUND
        if not content:
            return True, "What should I append?"
        if not self._confirm(f'Append to "{path}" in your Obsidian vault?'):
            return True, CANCELLED
        return True, self._call_tool(lambda: self.tools.obsidian_append(note, content))

    def _try_search_notes(self, request: str) -> tuple[bool, str]:
        match = _OBS_SEARCH.match(request)
        if not match:
            return False, ""
        query = (match.group("q") or "").strip(" \t\"'")
        if not query:
            return True, "What should I search your notes for?"
        return True, self._call_tool(lambda: self.tools.obsidian_search(query))

    def _try_read_note(self, request: str) -> tuple[bool, str]:
        match = _OBS_READ.match(request)
        if not match:
            return False, ""
        note = match.group("note").strip(" \t\"'")
        if not note:
            return True, NO_NOTE
        return True, self._call_tool(lambda: self.tools.obsidian_read(note))

    def _try_google(self, request: str) -> tuple[bool, str]:
        match = _GOOGLE.match(request)
        if not match:
            return False, ""
        query = match.group("q").strip(" \t\"'")
        if not query:
            return True, "What should I search for?"
        return True, self._call_tool(lambda: self.tools.google_search(query))

    def _try_open_app(self, request: str) -> tuple[bool, str]:
        match = _OPEN_APP.match(request)
        if not match:
            return False, ""
        name = match.group("app").strip()
        if not name or not self.tools.is_known_app(name):
            # Not an obvious app command -- let the model answer instead.
            return False, ""
        return True, self._call_tool(lambda: self.tools.open_app(name))

    # -- helpers --------------------------------------------------------

    def _confirm(self, question: str) -> bool:
        """Only obsidian_create and obsidian_append ask; everything else runs."""
        if self.confirm is None:
            return False
        try:
            return parse_yes(self.confirm(question))
        except Exception:
            return False

    @staticmethod
    def _call_tool(call) -> str:
        """Run a tool and turn any clean failure into plain English."""
        try:
            return str(call())
        except ObsidianError as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - never let a tool kill the loop
            return f"That didn't work: {exc}"

    # -- Ollama ---------------------------------------------------------

    def messages(self) -> list[dict[str, str]]:
        """System prompt plus the trimmed conversation history."""
        return [{"role": "system", "content": self.system_prompt}] + self.history

    def _ask_ollama(self, request: str) -> str:
        self.history.append({"role": "user", "content": request})
        self._trim_history()
        try:
            response = self.ollama.chat(self.messages())
        except OllamaUnavailable:
            self.history.pop()
            return OLLAMA_NOT_RUNNING
        except ModelNotFound as exc:
            self.history.pop()
            return str(exc)
        except OllamaError as exc:
            self.history.pop()
            return f"Ollama error: {exc}"

        answer = (getattr(response.message, "content", "") or "").strip() or NO_ANSWER
        self.history.append({"role": "assistant", "content": answer})
        self._trim_history()
        return answer

    def _trim_history(self) -> None:
        if len(self.history) > self.max_history:
            del self.history[: len(self.history) - self.max_history]