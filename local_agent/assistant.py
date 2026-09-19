"""Command router and conversation controller.

Recognition lives in ``commands.py`` (a pure vocabulary). This file decides what
to *do* with a recognised intent and is the only place that talks to tools:

    input (typed or STT) -> commands.recognize() -> tool or Ollama -> response

There is no agent loop, no manager, no event bus. Confirmation is asked in one
place, for the two file-writing intents only.
"""

from __future__ import annotations

from local_agent.commands import (
    CANCEL,
    CLEAR_CHAT,
    DIAGNOSTIC,
    GOODBYE,
    GOOGLE_SEARCH,
    GREETING,
    HELP,
    MODEL_INFO,
    OBSIDIAN_APPEND,
    OBSIDIAN_CREATE,
    OBSIDIAN_LIST,
    OBSIDIAN_READ,
    OBSIDIAN_SEARCH,
    OLLAMA_STATUS,
    OPEN_APP,
    OPEN_FOLDER,
    OPEN_WEBSITE,
    REPEAT,
    SHELL_BLOCKED,
    SPEAK_STOP,
    STATUS,
    THANKS,
    VOICE_OFF,
    VOICE_ON,
    Match,
    recognize,
    squeeze,
)
from local_agent.obsidian import NOTE_NOT_FOUND, ObsidianError
from local_agent.llm import ModelNotFound, OllamaError, OllamaUnavailable

OLLAMA_NOT_RUNNING = "Ollama is not running. Start Ollama and try again."
CANCELLED = "Okay, cancelled."
NO_ANSWER = "I don't have an answer for that."
NO_NOTE = "Which note do you mean?"
NO_QUERY = "What should I search for?"
NO_NOTE_QUERY = "What should I search your notes for?"
NOTHING_TO_REPEAT = "I haven't said anything yet."
VOICE_ON_MESSAGE = "Voice mode on. Press Enter and speak."
VOICE_OFF_MESSAGE = "Voice mode off. Replies will not be spoken."
VOICE_UNAVAILABLE = "Voice is not available in this session."
SHELL_REFUSED = (
    "I don't open shells or terminals. I can open apps, search the web, "
    "or work with your notes."
)
MAX_HISTORY_MESSAGES = 12

DEFAULT_SYSTEM_PROMPT = (
    "You are a concise, practical assistant running locally on the user's "
    "Windows laptop. Answer in plain text, lead with the answer, and keep it "
    "short unless the user asks for detail."
)

HELP_TEXT = """I can do these things:

Apps and folders
  open chrome / launch notepad / start my code editor
  open downloads / open my documents folder

Web
  search Google for Python internships
  google Python decorators / look up mutual funds

Your Obsidian notes
  search my notes for portfolio analysis
  read my note called Investment Analysis
  create an Obsidian note called Investment Ideas     (asks first)
  append this to my Investment Ideas note: ...        (asks first)
  list my notes

Assistant
  status / check Ollama / what model are you using
  start listening / stop listening / repeat that
  clear chat / help

Anything else goes to the local model as a normal question."""

_YES_WORDS = {
    "y", "yes", "yeah", "yep", "yup", "sure", "ok", "okay",
    "confirm", "confirmed", "go", "go ahead", "do it", "proceed",
}


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
    """Routes one request at a time and keeps a small conversation history.

    Both typed text and speech end up in :meth:`handle`, so there is exactly one
    router for the whole assistant.
    """

    def __init__(
        self,
        ollama,
        tools,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        confirm=default_confirm,
        max_history: int = MAX_HISTORY_MESSAGES,
        status=None,
        voice=None,
    ) -> None:
        self.ollama = ollama
        self.tools = tools
        self.system_prompt = system_prompt
        self.confirm = confirm
        self.max_history = max(2, int(max_history))
        self.status = status
        self.voice = voice
        self.history: list[dict[str, str]] = []

        # Set by the voice intents; None means "use the config default".
        self.voice_enabled: bool | None = None
        # Set by GOODBYE; main.py stops the loop when this is true.
        self.should_exit = False
        # Used by REPEAT.
        self.last_response = ""

        self._handlers = {
            OPEN_APP: self._do_open_app,
            OPEN_WEBSITE: self._do_open_website,
            OPEN_FOLDER: self._do_open_folder,
            SHELL_BLOCKED: self._do_shell_blocked,
            GOOGLE_SEARCH: self._do_google_search,
            OBSIDIAN_SEARCH: self._do_obsidian_search,
            OBSIDIAN_READ: self._do_obsidian_read,
            OBSIDIAN_LIST: self._do_obsidian_list,
            OBSIDIAN_CREATE: self._do_obsidian_create,
            OBSIDIAN_APPEND: self._do_obsidian_append,
            HELP: self._do_help,
            STATUS: self._do_status,
            OLLAMA_STATUS: self._do_ollama_status,
            MODEL_INFO: self._do_model_info,
            DIAGNOSTIC: self._do_diagnostic,
            VOICE_ON: self._do_voice_on,
            VOICE_OFF: self._do_voice_off,
            REPEAT: self._do_repeat,
            SPEAK_STOP: self._do_speak_stop,
            CLEAR_CHAT: self._do_clear_chat,
            CANCEL: self._do_cancel,
            GREETING: self._do_greeting,
            THANKS: self._do_thanks,
            GOODBYE: self._do_goodbye,
        }
        self._diagnostics = {
            "backend": self._diag_backend,
            "ollama": self._diag_backend,
            "model": self._diag_model,
            "obsidian": self._diag_obsidian,
            "microphone": self._diag_microphone,
            "voice": self._diag_microphone,
            "stt": self._diag_stt,
            "speaker": self._diag_speaker,
            "browser": self._diag_browser,
            "apps": self._diag_apps,
        }

    # -- public API -----------------------------------------------------

    def handle(self, text: str) -> str:
        """Turn one line of input (typed or transcribed) into one response."""
        request = squeeze(text)
        if not request:
            return ""
        match = recognize(request)
        response = (
            self._ask_ollama(request) if match is None else self._dispatch(match, request)
        )
        if response:
            self.last_response = response
        return response

    def reset(self) -> None:
        """Forget the conversation (not the notes)."""
        self.history.clear()

    def _dispatch(self, match: Match, request: str) -> str:
        handler = self._handlers.get(match.intent)
        if handler is None:
            # Unknown intent: never guess, just ask the model.
            return self._ask_ollama(request)
        return handler(match)

    # -- apps, websites, folders ----------------------------------------

    def _do_open_app(self, match: Match) -> str:
        return self._call_tool(lambda: self.tools.open_app(match.value))

    def _do_open_website(self, match: Match) -> str:
        return self._call_tool(lambda: self.tools.open_website(match.value))

    def _do_open_folder(self, match: Match) -> str:
        return self._call_tool(lambda: self.tools.open_folder(match.value))

    def _do_shell_blocked(self, match: Match) -> str:
        return SHELL_REFUSED

    def _do_google_search(self, match: Match) -> str:
        if not match.value:
            return NO_QUERY
        return self._call_tool(lambda: self.tools.google_search(match.value))

    # -- Obsidian -------------------------------------------------------

    def _do_obsidian_search(self, match: Match) -> str:
        if not match.value:
            return NO_NOTE_QUERY
        return self._call_tool(lambda: self.tools.obsidian_search(match.value))

    def _do_obsidian_read(self, match: Match) -> str:
        if not match.value:
            return NO_NOTE
        return self._call_tool(lambda: self.tools.obsidian_read(match.value))

    def _do_obsidian_list(self, match: Match) -> str:
        return self._call_tool(lambda: self.tools.obsidian_list())

    def _do_obsidian_create(self, match: Match) -> str:
        if not match.value:
            return "What should the note be called?"
        try:
            path = self.tools.obsidian_path(match.value)
        except ObsidianError as exc:
            return str(exc)
        if not self._confirm(f'Create "{path}" in your Obsidian vault?'):
            return CANCELLED
        return self._call_tool(
            lambda: self.tools.obsidian_create(match.value, match.extra)
        )

    def _do_obsidian_append(self, match: Match) -> str:
        if not match.value:
            return NO_NOTE
        try:
            path = self.tools.obsidian_path(match.value)
            exists = self.tools.obsidian_exists(match.value)
        except ObsidianError as exc:
            return str(exc)
        if not exists:
            return NOTE_NOT_FOUND
        if not match.extra:
            return f'What should I append to "{path}"?'
        if not self._confirm(f'Append to "{path}" in your Obsidian vault?'):
            return CANCELLED
        return self._call_tool(
            lambda: self.tools.obsidian_append(match.value, match.extra)
        )

    # -- help, status, model --------------------------------------------

    def _do_help(self, match: Match) -> str:
        return HELP_TEXT

    def _do_status(self, match: Match) -> str:
        if callable(self.status):
            try:
                return str(self.status())
            except Exception as exc:  # noqa: BLE001 - status must never crash
                return f"I couldn't read the status ({exc})."
        return "\n".join(
            [
                f"Ollama: {'running' if not self._ollama_problem() else 'not connected'}",
                f"Model: {self._model_name()}",
                f"Obsidian: {self._obsidian_state()}",
                f"Voice: {self._voice_state()}",
            ]
        )

    def _do_ollama_status(self, match: Match) -> str:
        problem = self._ollama_problem()
        if problem:
            return problem
        return f"Ollama is running. Model: {self._model_name()}"

    def _do_model_info(self, match: Match) -> str:
        if self._ollama_problem():
            return f"Model: {self._model_name()}. {OLLAMA_NOT_RUNNING}"
        return f"Model: {self._model_name()} (served by Ollama on {self._ollama_host()})"

    # -- diagnostics ("test the microphone" and friends) ----------------
    # Every check only reads state that already exists: nothing is launched,
    # opened, recorded or modified.

    def _do_diagnostic(self, match: Match) -> str:
        check = self._diagnostics.get(match.value or "backend")
        if check is None:
            return "I don't have a test for that."
        try:
            return check()
        except Exception as exc:  # noqa: BLE001 - a test must never crash the loop
            return f"That test could not run ({exc})."

    def _diag_backend(self) -> str:
        state = "unavailable" if self._ollama_problem() else "ready"
        return (
            f"Backend is running. Ollama: {state}. "
            f"Model: {self._model_name()}. Obsidian: {self._obsidian_state()}."
        )

    def _diag_model(self) -> str:
        return self._do_model_info(Match(MODEL_INFO))

    def _diag_obsidian(self) -> str:
        state = self._obsidian_state()
        if state == "not configured":
            return "Obsidian is not configured. Set obsidian.vault in config.json."
        return f"Obsidian is configured at {state}."

    def _diag_microphone(self) -> str:
        if self.voice is None:
            return "Voice is not available in this session."
        if self._voice_available():
            return "Microphone is ready. Press Enter and speak to try it."
        return f"Microphone is unavailable ({self._voice_reason()})."

    def _diag_stt(self) -> str:
        if self.voice is None:
            return "Speech recognition is not available in this session."
        if self._voice_available():
            return "Speech recognition is ready (faster-whisper)."
        return f"Speech recognition is unavailable ({self._voice_reason()})."

    def _diag_speaker(self) -> str:
        if self.voice is None:
            return "Text to speech is not available in this session."
        if getattr(self.voice, "tts_enabled", False):
            return "Text to speech is enabled in config.json."
        return "Text to speech is disabled in config.json."

    def _diag_browser(self) -> str:
        return (
            "I won't open a browser just for a test. Say "
            "'search Google for test' to try it."
        )

    def _diag_apps(self) -> str:
        known = getattr(self.tools, "is_known_app", None)
        if callable(known) and known("notepad"):
            return "App launcher is ready (fixed alias table, no shell)."
        return "App launcher is unavailable."

    # -- voice and conversation -----------------------------------------

    def _do_voice_on(self, match: Match) -> str:
        if self.voice is None:
            return VOICE_UNAVAILABLE
        if not self._voice_available():
            return f"Voice is unavailable ({self._voice_reason()})."
        self.voice_enabled = True
        return VOICE_ON_MESSAGE

    def _do_voice_off(self, match: Match) -> str:
        self.voice_enabled = False
        self._stop_speaking()
        return VOICE_OFF_MESSAGE

    def _do_repeat(self, match: Match) -> str:
        return self.last_response or NOTHING_TO_REPEAT

    def _do_speak_stop(self, match: Match) -> str:
        self._stop_speaking()
        return "Stopped speaking."

    def _do_clear_chat(self, match: Match) -> str:
        self.reset()
        return "Conversation cleared."

    def _do_cancel(self, match: Match) -> str:
        self._stop_speaking()
        return CANCELLED

    def _do_greeting(self, match: Match) -> str:
        return "Hello. What can I help you with?"

    def _do_thanks(self, match: Match) -> str:
        return "You're welcome."

    def _do_goodbye(self, match: Match) -> str:
        self.should_exit = True
        return "Goodbye."

    # -- helpers ---------------------------------------------------------

    def _confirm(self, question: str) -> bool:
        """Only obsidian_create and obsidian_append ask; everything else runs."""
        if self.confirm is None:
            return False
        try:
            return parse_yes(self.confirm(question))
        except Exception:
            return False

    def _stop_speaking(self) -> None:
        stop = getattr(self.voice, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:  # noqa: BLE001 - a dead speaker is not an error
                pass

    @staticmethod
    def _call_tool(call) -> str:
        """Run a tool and turn any clean failure into plain English."""
        try:
            return str(call())
        except ObsidianError as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - never let a tool kill the loop
            return f"That didn't work: {exc}"

    def _model_name(self) -> str:
        return str(getattr(self.ollama, "model", "unknown"))

    def _ollama_host(self) -> str:
        return str(getattr(self.ollama, "host", "127.0.0.1"))

    def _ollama_problem(self) -> str:
        """"" when Ollama is reachable, otherwise a message for the user."""
        check = getattr(self.ollama, "check", None)
        if callable(check):
            try:
                return str(check() or "")
            except Exception as exc:  # noqa: BLE001
                return f"Ollama error: {exc}"
        available = getattr(self.ollama, "is_available", None)
        if callable(available):
            try:
                return "" if available() else OLLAMA_NOT_RUNNING
            except Exception as exc:  # noqa: BLE001
                return f"Ollama error: {exc}"
        return ""

    def _obsidian_state(self) -> str:
        obsidian = getattr(self.tools, "obsidian", None)
        describe = getattr(obsidian, "describe", None)
        if callable(describe):
            return str(describe())
        return "configured" if getattr(obsidian, "configured", False) else "not configured"

    def _voice_available(self) -> bool:
        return bool(getattr(self.voice, "available", False))

    def _voice_reason(self) -> str:
        return str(getattr(self.voice, "reason", "") or "voice is not available")

    def _voice_state(self) -> str:
        if self.voice is None:
            return "unavailable"
        if self._voice_available():
            return "ready"
        return f"unavailable ({self._voice_reason()})"

    # -- Ollama ----------------------------------------------------------

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
