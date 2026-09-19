"""Interactive CLI loop for the local assistant.

Provides the REPL: reads user input, dispatches to the assistant, and handles
all terminal UX: readline history, Ctrl+C, Ctrl+D, slash commands, and
session persistence.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Enable readline for up/down arrow history on all platforms where available.
try:
    import readline as _readline  # noqa: F401  (side-effect import)
except ImportError:
    pass  # Windows without pyreadline — arrows won't work, everything else will.

_PROMPT = "You > "
_HISTORY_DIR = Path(__file__).resolve().parent.parent / "data" / "history"

# ---------------------------------------------------------------------------
# Slash command dispatch
# ---------------------------------------------------------------------------

_SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/clear": "Clear the current conversation",
    "/reset": "Reset assistant state (same as /clear)",
    "/status": "Show assistant and provider status",
    "/model": "Show the active model",
    "/history": "List saved conversation sessions",
    "/exit": "Exit the assistant",
    "/quit": "Exit the assistant",
    "/q": "Exit the assistant",
}

_HELP_TEXT = """
Available commands:
  /help     Show available commands
  /clear    Clear the current conversation
  /reset    Reset assistant state
  /status   Show assistant/provider status
  /model    Show the active model
  /history  List saved conversation sessions
  /exit     Exit the assistant

Anything that is not a command is sent to the assistant as a question.
You can also say natural phrases like:
  • open chrome          • search Google for Python tutorials
  • find my notes about  • read my note called Investment Analysis
  • create a note called • what is ROCE?
""".strip()


def _handle_slash(command: str, assistant) -> bool:
    """Handle a slash command. Returns True if the session should exit."""
    cmd = command.strip().lower()

    if cmd in ("/exit", "/quit", "/q"):
        print("Goodbye.")
        return True

    if cmd in ("/clear", "/reset"):
        assistant.reset()
        print("Conversation cleared.")
        return False

    if cmd == "/help":
        print(_HELP_TEXT)
        return False

    if cmd == "/status":
        # Re-use the assistant's own status logic
        match_obj = _make_status_match()
        response = assistant._do_status(match_obj)
        print(response)
        return False

    if cmd == "/model":
        model = assistant._model_name()
        host = assistant._ollama_host()
        print(f"Model: {model}  (Ollama at {host})")
        return False

    if cmd == "/history":
        _show_history()
        return False

    # Unknown slash command → tell the user rather than silently swallowing it.
    print(f"Unknown command: {command}  (type /help for available commands)")
    return False


def _make_status_match():
    """Create a minimal Match object for the STATUS intent."""
    # Import here to avoid circular issues at module load.
    from local_agent.commands import Match, STATUS
    return Match(intent=STATUS)


def _show_history() -> None:
    """List saved session files."""
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(_HISTORY_DIR.glob("*.jsonl"), reverse=True)
    if not files:
        print("No saved sessions yet.")
        return
    print(f"Saved sessions ({len(files)}):")
    for f in files[:20]:
        size = f.stat().st_size
        print(f"  {f.stem}  ({size} bytes)")


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------

class _SessionRecorder:
    """Appends conversation turns to a JSONL file as the session progresses."""

    def __init__(self) -> None:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = _HISTORY_DIR / f"{stamp}.jsonl"
        self._file = None

    def _open(self):
        if self._file is None:
            try:
                self._file = self._path.open("a", encoding="utf-8")
            except OSError:
                pass

    def record(self, role: str, content: str) -> None:
        self._open()
        if self._file is None:
            return
        try:
            self._file.write(json.dumps({"role": role, "content": content}) + "\n")
            self._file.flush()
        except OSError:
            pass

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None


# ---------------------------------------------------------------------------
# Main REPL
# ---------------------------------------------------------------------------

def _print_banner() -> None:
    width = 44
    print("┌" + "─" * width + "┐")
    print("│" + " Local AI Assistant ".center(width) + "│")
    print("└" + "─" * width + "┘")


def run(assistant, *, record_session: bool = True) -> None:
    """Enter the interactive assistant loop.

    ``assistant`` must implement:
      • handle(text: str) -> str
      • reset() -> None
      • should_exit: bool
      • _model_name(), _ollama_host(), _do_status(match)
    """
    _print_banner()
    print()
    print("Assistant ready. Type /help for commands or ask a question.")
    print()

    recorder = _SessionRecorder() if record_session else None

    try:
        _repl(assistant, recorder)
    finally:
        if recorder:
            recorder.close()


def _repl(assistant, recorder) -> None:
    while True:
        # ---------- read input ----------
        try:
            user_input = input(_PROMPT)
        except EOFError:
            # Ctrl+D
            print()
            print("Goodbye.")
            break
        except KeyboardInterrupt:
            # Ctrl+C at the prompt — just continue
            print()
            continue

        text = user_input.strip()
        if not text:
            # Empty line: original project supported voice here.
            # We keep it simple: just re-prompt.
            continue

        # ---------- slash commands ----------
        if text.startswith("/"):
            should_exit = _handle_slash(text, assistant)
            if should_exit:
                break
            continue

        # ---------- send to assistant ----------
        if recorder:
            recorder.record("user", text)

        try:
            response = assistant.handle(text)
        except KeyboardInterrupt:
            # Ctrl+C during model generation — cancel and continue.
            print("\n[Cancelled]")
            continue
        except Exception as exc:  # noqa: BLE001 — never let a bug kill the loop
            print(f"[Error] Something went wrong: {exc}")
            continue

        if response:
            print(f"Assistant > {response}")
            print()
            if recorder:
                recorder.record("assistant", response)

        # Check if the assistant wants to exit (e.g. "goodbye" phrase).
        if getattr(assistant, "should_exit", False):
            assistant.should_exit = False
            break
