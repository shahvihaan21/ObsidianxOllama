"""Core routing tests: deterministic commands, confirmation, and Ollama fallback.

Nothing here touches Ollama, a browser, a microphone or a real vault.
"""

import pytest

from app.core import CANCELLED, OLLAMA_NOT_RUNNING, Assistant
from app.ollama import ChatMessage, ChatResponse, ModelNotFound, OllamaUnavailable


class FakeOllama:
    def __init__(
        self,
        answer="Return on capital employed.",
        error=None,
        problem="",
        model="qwen3:1.7b",
        host="http://127.0.0.1:11434",
    ):
        self.answer = answer
        self.error = error
        self.problem = problem  # "" = healthy, otherwise the message to report
        self.model = model
        self.host = host
        self.calls = []

    def check(self):
        return self.problem

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return ChatResponse(message=ChatMessage(role="assistant", content=self.answer))


class FakeVoice:
    def __init__(self, available=True, reason="", tts_enabled=True):
        self.available = available
        self.reason = reason
        self.tts_enabled = tts_enabled
        self.stopped = 0

    def stop(self):
        self.stopped += 1


class FakeTools:
    """Records what the router asked for. Nothing reaches the machine."""

    KNOWN_APPS = {"chrome", "notepad", "vs code"}

    def __init__(self, note_exists=True):
        self.calls = []
        self.note_exists = note_exists
        self.obsidian = None

    def is_known_app(self, name):
        return name.strip().lower() in self.KNOWN_APPS

    def open_app(self, name):
        self.calls.append(("open_app", name))
        return "Opening Chrome."

    def open_website(self, name):
        self.calls.append(("open_website", name))
        return "Opening Google."

    def open_folder(self, name):
        self.calls.append(("open_folder", name))
        return "Opening your Downloads folder."

    def google_search(self, query):
        self.calls.append(("google_search", query))
        return "Opening Google search."

    def obsidian_search(self, query):
        self.calls.append(("obsidian_search", query))
        return "Found 1 note(s):\n- Portfolio.md"

    def obsidian_read(self, note):
        self.calls.append(("obsidian_read", note))
        return "# Investment Analysis"

    def obsidian_list(self):
        self.calls.append(("obsidian_list",))
        return "You have 1 note(s):\n- Portfolio.md"

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


def build(confirm=lambda question: True, tools=None, ollama=None, voice=None, status=None):
    tools = tools or FakeTools()
    ollama = ollama or FakeOllama()
    return (
        Assistant(
            ollama=ollama, tools=tools, confirm=confirm, voice=voice, status=status
        ),
        tools,
        ollama,
    )


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
    # "flstudio" is not in the app table, so this is not an obvious command.
    assistant.handle("open flstudio")
    assert tools.calls == []
    assert len(ollama.calls) == 1


def test_supported_app_is_deterministic():
    assistant, tools, ollama = build()
    assistant.handle("open spotify")
    assert tools.calls == [("open_app", "spotify")]
    assert ollama.calls == []


def test_ollama_unavailable_is_graceful():
    offline = FakeOllama(error=OllamaUnavailable("http://127.0.0.1:11434"))
    assistant, _, _ = build(ollama=offline)
    assert assistant.handle("what is ROCE?") == OLLAMA_NOT_RUNNING


def test_missing_model_is_reported_clearly():
    missing = FakeOllama(error=ModelNotFound("qwen3:1.7b"))
    assistant, _, _ = build(ollama=missing)
    # A real question reaches Ollama; "hello" is answered locally by design.
    assert "ollama pull qwen3:1.7b" in assistant.handle("what is ROCE?")


def test_empty_input_is_ignored():
    assistant, tools, ollama = build()
    assert assistant.handle("   ") == ""
    assert tools.calls == []
    assert ollama.calls == []


# -- one test per command category (see commands.py) --------------------


def test_open_website_routes_to_the_website_tool():
    assistant, tools, ollama = build()
    assert assistant.handle("open google") == "Opening Google."
    assert tools.calls == [("open_website", "google")]
    assert ollama.calls == []


@pytest.mark.parametrize("phrase", ["go to youtube", "visit youtube", "take me to youtube"])
def test_website_phrasings(phrase):
    assistant, tools, _ = build()
    assistant.handle(phrase)
    assert tools.calls == [("open_website", "youtube")]


def test_open_folder_routes_to_the_folder_tool():
    assistant, tools, _ = build()
    assistant.handle("open my downloads folder")
    assert tools.calls == [("open_folder", "downloads")]


@pytest.mark.parametrize("phrase", ["open powershell", "open command prompt", "open terminal"])
def test_shell_requests_are_refused_without_running_anything(phrase):
    assistant, tools, ollama = build()
    assert "shell" in assistant.handle(phrase).lower()
    assert tools.calls == []
    assert ollama.calls == []


def test_obsidian_list_routing():
    assistant, tools, ollama = build()
    response = assistant.handle("list my notes")
    assert "Portfolio.md" in response
    assert tools.calls == [("obsidian_list",)]
    assert ollama.calls == []


def test_help_lists_capabilities_without_calling_ollama():
    assistant, tools, ollama = build()
    response = assistant.handle("what can you do")
    assert "search Google for" in response
    assert tools.calls == []
    assert ollama.calls == []


def test_status_uses_the_injected_status_provider():
    assistant, _, ollama = build(status=lambda: "Ollama: connected")
    assert assistant.handle("system status") == "Ollama: connected"
    assert ollama.calls == []


def test_status_falls_back_to_a_plain_report():
    assistant, _, _ = build()
    assert "Model: qwen3:1.7b" in assistant.handle("status")


def test_ollama_status_reports_a_problem():
    assistant, _, _ = build(ollama=FakeOllama(problem=OLLAMA_NOT_RUNNING))
    assert assistant.handle("check Ollama") == OLLAMA_NOT_RUNNING


def test_ollama_status_reports_health():
    assistant, _, _ = build()
    assert "Ollama is running" in assistant.handle("is Ollama running")


def test_model_info_names_the_model():
    assistant, _, _ = build()
    assert "qwen3:1.7b" in assistant.handle("what model are you using")


def test_voice_on_and_off_flags():
    voice = FakeVoice()
    assistant, _, _ = build(voice=voice)
    assert assistant.voice_enabled is None
    assert "Voice mode on" in assistant.handle("start listening")
    assert assistant.voice_enabled is True
    assert "Voice mode off" in assistant.handle("stop listening")
    assert assistant.voice_enabled is False


def test_voice_on_when_unavailable():
    assistant, _, _ = build(voice=FakeVoice(available=False, reason="no microphone"))
    assert "unavailable" in assistant.handle("start listening").lower()
    assert assistant.voice_enabled is None


def test_repeat_repeats_the_last_answer():
    assistant, _, _ = build()
    assistant.handle("what is ROCE?")
    assert assistant.handle("repeat that") == "Return on capital employed."


def test_repeat_with_nothing_to_repeat():
    assistant, _, _ = build()
    assert "haven't said anything" in assistant.handle("repeat that")


def test_stop_speaking_stops_the_voice():
    voice = FakeVoice()
    assistant, _, _ = build(voice=voice)
    assert assistant.handle("stop speaking") == "Stopped speaking."
    assert voice.stopped == 1


def test_clear_chat_forgets_the_history():
    assistant, _, ollama = build()
    assistant.handle("what is ROCE?")
    assert "cleared" in assistant.handle("clear chat").lower()
    assistant.handle("and ROE?")
    assert [m["role"] for m in ollama.calls[-1]] == ["system", "user"]


def test_cancel_needs_no_tool_and_stops_speech():
    voice = FakeVoice()
    assistant, tools, ollama = build(voice=voice)
    assert assistant.handle("never mind") == CANCELLED
    assert tools.calls == []
    assert ollama.calls == []
    assert voice.stopped == 1


def test_greeting_and_thanks_need_no_ollama():
    assistant, _, ollama = build()
    assert "Hello" in assistant.handle("hello")
    assert "welcome" in assistant.handle("thank you").lower()
    assert ollama.calls == []


def test_goodbye_sets_the_exit_flag():
    assistant, _, _ = build()
    assert assistant.handle("goodbye") == "Goodbye."
    assert assistant.should_exit is True


def test_diagnostics_report_without_side_effects():
    assistant, tools, ollama = build(voice=FakeVoice(available=False, reason="no microphone"))
    assert "unavailable" in assistant.handle("test microphone")
    assert "ready" in assistant.handle("test app launcher").lower()
    assert tools.calls == []
    assert ollama.calls == []


def test_search_without_a_query_asks_for_one():
    assistant, tools, _ = build()
    assert assistant.handle("look this up") == "What should I search for?"
    assert tools.calls == []


def test_note_search_without_a_query_asks_for_one():
    assistant, tools, _ = build()
    assert assistant.handle("search my notes") == "What should I search your notes for?"
    assert tools.calls == []


def test_append_without_content_asks_for_content():
    assistant, tools, _ = build()
    response = assistant.handle("add this to my Investment Ideas note")
    assert "What should I append" in response
    assert tools.calls == []
