"""Core routing tests: deterministic commands, confirmation, and Ollama fallback.

Nothing here touches Ollama, a browser, a microphone or a real vault.
"""

import pytest

from core import CANCELLED, OLLAMA_NOT_RUNNING, Assistant
from ollama import ChatMessage, ChatResponse, ModelNotFound, OllamaUnavailable


class FakeOllama:
    def __init__(self, answer="Return on capital employed.", error=None):
        self.answer = answer
        self.error = error
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return ChatResponse(message=ChatMessage(role="assistant", content=self.answer))


class FakeTools:
    """Records what the router asked for. Nothing reaches the machine."""

    KNOWN_APPS = {"chrome", "notepad", "vs code"}

    def __init__(self, note_exists=True):
        self.calls = []
        self.note_exists = note_exists

    def is_known_app(self, name):
        return name.strip().lower() in self.KNOWN_APPS

    def open_app(self, name):
        self.calls.append(("open_app", name))
        return "Opening Chrome."

    def google_search(self, query):
        self.calls.append(("google_search", query))
        return "Opening Google search."

    def obsidian_search(self, query):
        self.calls.append(("obsidian_search", query))
        return "Found 1 note(s):\n- Portfolio.md"

    def obsidian_read(self, note):
        self.calls.append(("obsidian_read", note))
        return "# Investment Analysis"

    def obsidian_create(self, note, content=""):
        self.calls.append(("obsidian_create", note, content))
        return 'Created "X.md" in your Obsidian vault.'

    def obsidian_append(self, note, content):
        self.calls.append(("obsidian_append", note, content))
        return 'Appended to "X.md".'

    def obsidian_exists(self, note):
        return self.note_exists

    def obsidian_path(self, note):
        return f"{note.strip()}.md"


def build(confirm=lambda question: True, tools=None, ollama=None):
    tools = tools or FakeTools()
    ollama = ollama or FakeOllama()
    return Assistant(ollama=ollama, tools=tools, confirm=confirm), tools, ollama


def test_question_is_routed_to_ollama():
    assistant, tools, ollama = build()
    assert assistant.handle("what is ROCE?") == "Return on capital employed."
    assert tools.calls == []
    assert len(ollama.calls) == 1
    assert ollama.calls[0][0]["role"] == "system"
    assert ollama.calls[0][-1] == {"role": "user", "content": "what is ROCE?"}


def test_conversation_history_is_kept():
    assistant, _, ollama = build()
    assistant.handle("what is ROCE?")
    assistant.handle("and ROCE versus ROE?")
    assert [m["role"] for m in ollama.calls[-1]] == ["system", "user", "assistant", "user"]


@pytest.mark.parametrize("phrase", ["open chrome", "launch chrome", "start chrome"])
def test_open_app_routes_to_the_app_tool(phrase):
    assistant, tools, ollama = build()
    assert assistant.handle(phrase) == "Opening Chrome."
    assert tools.calls == [("open_app", "chrome")]
    assert ollama.calls == []


@pytest.mark.parametrize(
    "phrase",
    [
        "search Google for Python internships",
        "search for Python internships",
        "search the web for Python internships",
        "look up Python internships",
    ],
)
def test_google_search_routing(phrase):
    assistant, tools, ollama = build()
    assistant.handle(phrase)
    assert tools.calls == [("google_search", "Python internships")]
    assert ollama.calls == []


@pytest.mark.parametrize(
    "phrase",
    [
        "find my notes about portfolio analysis",
        "search my notes for portfolio analysis",
    ],
)
def test_obsidian_search_routing(phrase):
    assistant, tools, ollama = build()
    response = assistant.handle(phrase)
    assert tools.calls == [("obsidian_search", "portfolio analysis")]
    assert "Portfolio.md" in response
    assert ollama.calls == []


def test_obsidian_read_routing():
    assistant, tools, ollama = build()
    response = assistant.handle("read my note called Investment Analysis")
    assert response == "# Investment Analysis"
    assert tools.calls == [("obsidian_read", "Investment Analysis")]
    assert ollama.calls == []


def test_obsidian_create_asks_for_confirmation():
    prompts = []

    def confirm(question):
        prompts.append(question)
        return True

    assistant, tools, _ = build(confirm=confirm)
    response = assistant.handle("create an Obsidian note called Investment Ideas")
    assert prompts == ['Create "Investment Ideas.md" in your Obsidian vault?']
    assert tools.calls == [("obsidian_create", "Investment Ideas", "")]
    assert "Created" in response


def test_obsidian_create_accepts_inline_content():
    assistant, tools, _ = build()
    assistant.handle("create a note called Investment Ideas with content Buy index funds")
    assert tools.calls == [("obsidian_create", "Investment Ideas", "Buy index funds")]


def test_obsidian_create_is_cancelled_when_declined():
    assistant, tools, _ = build(confirm=lambda question: False)
    assert assistant.handle("create an Obsidian note called Investment Ideas") == CANCELLED
    assert tools.calls == []


def test_obsidian_append_asks_for_confirmation():
    prompts = []
    assistant, tools, _ = build(confirm=lambda question: prompts.append(question) or True)
    response = assistant.handle("append this to my Investment Ideas note: buy index funds")
    assert prompts == ['Append to "Investment Ideas.md" in your Obsidian vault?']
    assert tools.calls == [("obsidian_append", "Investment Ideas", "buy index funds")]
    assert "Appended" in response


def test_obsidian_append_is_cancelled_when_declined():
    assistant, tools, _ = build(confirm=lambda question: False)
    assert assistant.handle("append this to my Investment Ideas note: hello") == CANCELLED
    assert tools.calls == []


def test_append_to_a_missing_note_never_prompts():
    prompts = []
    tools = FakeTools(note_exists=False)
    assistant, _, _ = build(
        confirm=lambda question: prompts.append(question) or True, tools=tools
    )
    assert assistant.handle("append this to my Missing note: hello") == "Note not found."
    assert prompts == []
    assert tools.calls == []


def test_unknown_app_falls_through_to_ollama():
    assistant, tools, ollama = build()
    assistant.handle("open spotify")
    assert tools.calls == []
    assert len(ollama.calls) == 1


def test_ollama_unavailable_is_graceful():
    offline = FakeOllama(error=OllamaUnavailable("http://127.0.0.1:11434"))
    assistant, _, _ = build(ollama=offline)
    assert assistant.handle("what is ROCE?") == OLLAMA_NOT_RUNNING


def test_missing_model_is_reported_clearly():
    missing = FakeOllama(error=ModelNotFound("qwen3:1.7b"))
    assistant, _, _ = build(ollama=missing)
    assert "ollama pull qwen3:1.7b" in assistant.handle("hello")


def test_empty_input_is_ignored():
    assistant, tools, ollama = build()
    assert assistant.handle("   ") == ""
    assert tools.calls == []
    assert ollama.calls == []
