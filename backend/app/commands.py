"""Command vocabulary for the local assistant -- RECOGNITION ONLY.

This file answers exactly one question: "does this sentence look like a command,
and if so, which one?" It never launches anything, never touches the filesystem,
never calls Ollama, and never touches the microphone or the speakers.

    typed text  ---+
                   |      (voice: STT -> text)
                   v
            commands.recognize()      <- this file (pure + deterministic)
                   v
                core.py               <- decides what to do, asks for confirmation
                   v
        tools.py / obsidian.py / ollama.py
                   v
                response

Typed input and speech both end up in ``core.Assistant.handle()``, so there is
exactly ONE router and ONE command vocabulary -- voice is not a second system.

How to extend this file
-----------------------
* fixed sentence, no variables -> append to ``COMMANDS["INTENT"]``
* sentence with a variable part -> append a regex to ``COMMAND_PATTERNS["INTENT"]``
  using the named groups ``(?P<q>..)`` / ``(?P<name>..)`` / ``(?P<note>..)`` /
  ``(?P<content>..)``
* new application -> add an alias to ``tools.APP_ALIASES``
* new website     -> add a URL to ``tools.WEBSITES``
* new folder      -> add a path to ``tools.FOLDERS``

App, website and folder names are read from ``tools.py`` so there is only one
place to edit them. Nothing here can execute anything: the worst a wrong match
can do is call a tool with a name that ``tools.py`` already knows.

Anything that does not match falls through to Ollama (see ``core.py``).
"""

from __future__ import annotations

import re
from typing import NamedTuple

from .tools import APP_ALIASES, FOLDERS, WEBSITES

# ---------------------------------------------------------------------------
# Intents
# ---------------------------------------------------------------------------
# One intent per capability. Many phrases map to one intent; no intent maps to
# more than one action (see core.py).

OPEN_APP = "OPEN_APP"                    # launch a known application
OPEN_WEBSITE = "OPEN_WEBSITE"            # open a known website
OPEN_FOLDER = "OPEN_FOLDER"              # open a known user folder
SHELL_BLOCKED = "SHELL_BLOCKED"          # a shell/terminal was asked for: refuse
GOOGLE_SEARCH = "GOOGLE_SEARCH"          # web search (Google is the engine)
OBSIDIAN_SEARCH = "OBSIDIAN_SEARCH"      # search the vault
OBSIDIAN_READ = "OBSIDIAN_READ"          # read one note
OBSIDIAN_CREATE = "OBSIDIAN_CREATE"      # create a note    (needs confirmation)
OBSIDIAN_APPEND = "OBSIDIAN_APPEND"      # append to a note (needs confirmation)
OBSIDIAN_LIST = "OBSIDIAN_LIST"          # list the notes in the vault
HELP = "HELP"                            # what can you do
STATUS = "STATUS"                        # overall status
OLLAMA_STATUS = "OLLAMA_STATUS"          # is Ollama running
MODEL_INFO = "MODEL_INFO"                # which model is in use
DIAGNOSTIC = "DIAGNOSTIC"                # "test the microphone" etc.
VOICE_ON = "VOICE_ON"                    # switch to voice mode
VOICE_OFF = "VOICE_OFF"                  # switch to text mode
REPEAT = "REPEAT"                        # say that again
SPEAK_STOP = "SPEAK_STOP"                # stop talking
CLEAR_CHAT = "CLEAR_CHAT"                # forget the conversation
CANCEL = "CANCEL"                        # never mind
GREETING = "GREETING"                    # hello
THANKS = "THANKS"                        # thank you
GOODBYE = "GOODBYE"                      # goodbye / quit


class Match(NamedTuple):
    """The result of recognition: which intent, and its arguments.

    value -- the app alias / website / folder / query / note name
    extra -- the content for OBSIDIAN_CREATE and OBSIDIAN_APPEND
    """

    intent: str
    value: str = ""
    extra: str = ""


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_TRAILING_NOISE = re.compile(r"[\s.?!,;:]+$")
_PLEASE = re.compile(r"\s+(?:please|thanks|thank you)$")


def normalize(text: str) -> str:
    """Lower-case, collapse whitespace, drop quotes and trailing noise.

    ``"  Open   Chrome, please?  "`` -> ``"open chrome"``
    """
    cleaned = " ".join(str(text or "").split()).strip().strip("\"'")
    # Repeat so "Open Chrome, please?" loses both the "please" and the comma.
    for _ in range(2):
        cleaned = _TRAILING_NOISE.sub("", cleaned)
        cleaned = _PLEASE.sub("", cleaned)
    return cleaned.strip().strip("\"'").strip().lower()


def squeeze(text: str) -> str:
    """Collapse whitespace but keep the original casing (for note names)."""
    return " ".join(str(text or "").split()).strip()


# ---------------------------------------------------------------------------
# Shared regex fragments (used to build COMMAND_PATTERNS below)
# ---------------------------------------------------------------------------

# Optional polite/wordy lead-in: "please", "can you", "hey assistant", ...
_F = (
    r"^(?:(?:please|hey|ok|okay|so|now)\s+|"
    r"(?:can|could|would)\s+you\s+|"
    r"hey\s+assistant\s+|"
    r"i\s+(?:want|would\s+like|need)\s+to\s+|"
    r"i'?d\s+like\s+to\s+|"
    r"let'?s\s+|"
    r"lets\s+)*"
)

# "the notes", "my Obsidian notes", "my vault", "obsidian", "memory"
_SCOPE = (
    r"(?:my\s+|the\s+|your\s+)?"
    r"(?:obsidian(?:\s+(?:notes?|vault))?|notes?|vault|memory|knowledge\s+base)"
)
# Relation word between the scope and the query.
_REL = (
    r"(?:for|about|on|containing|mentioning|with|related\s+to|regarding|"
    r"that\s+mention|that\s+contain|which\s+mention)"
)
# Optional "information", "anything", "notes" filler.
_INFO = r"(?:information|info|anything|something|details|notes|references)?\s*"
# Guard: "search my notes" must never become a web search.
_NOT_NOTES = (
    r"(?!(?:my\s+|the\s+|your\s+)?(?:notes?|vault|obsidian|memory)\b)"
)

# Verbs ---------------------------------------------------------------------
_OPEN_VERBS = (
    r"(?:open|launch|start|run|bring\s+up|pull\s+up|fire\s+up|"
    r"go\s+to|goto|visit|navigate\s+to|take\s+me\s+to|jump\s+to|show\s+me)"
)
_SEARCH_VERBS = (
    r"(?:search|find|look\s+up|look\s+for|look\s+through|look\s+in|browse|check|"
    r"grep|scan|read|show|see\s+if\s+i\s+have|do\s+i\s+have)"
)
_READ_VERBS = (
    r"(?:read|open|show|display|fetch|get|view|load|pull\s+up|bring\s+up|print)"
)
_CREATE_VERBS = r"(?:create|make|add|start|begin|write|set\s+up|new)"
_APPEND_VERBS = r"(?:add|append|save|put|write|insert|attach|note)"

# Articles / labels ---------------------------------------------------------
_ART = r"(?:me\s+)?(?:a\s+|an\s+|the\s+)?(?:new\s+|another\s+)?"
_NOTE_WORD = r"(?:obsidian\s+)?notes?"
_LABEL = r"(?:\s+(?:called|named|titled|labelled|labeled|for|about|on|to))?"
# Everything after an explicit separator becomes the note content.
_CONTENT = (
    r"(?:\s*(?:[:,-]|\bwith\s+(?:the\s+)?(?:content|text|body)\b|"
    r"\bcontaining\b|\bsaying\b|\bthat\s+says?\b|\bthat\s+contains\b|"
    r"\bwith\s+the\s+text\b)\s*(?P<content>.*?))?"
)
# Notes are always markdown; keep these free of ':' so they cannot eat content.
_NOTE_NAME = r"(?P<note>[^:]+?)"
_NAME = r"(?P<name>[^:]+?)"
_QUERY = r"(?P<q>\S.*?)"


# ---------------------------------------------------------------------------
# Fixed targets
# ---------------------------------------------------------------------------
# Friendly phrases that mean an app or a website. Applications, websites and
# folders themselves live in tools.py (single source of truth).

GENERIC_APP_PHRASES: dict[str, str] = {
    "browser": "chrome",
    "the browser": "chrome",
    "my browser": "chrome",
    "web browser": "chrome",
    "internet browser": "chrome",
    "code editor": "vs code",
    "my code editor": "vs code",
    "my editor": "vs code",
    "editor": "vs code",
    "my ide": "vs code",
    "ide": "vs code",
    "notes app": "obsidian",
    "my notes app": "obsidian",
    "my obsidian": "obsidian",
    "music": "spotify",
    "my music": "spotify",
    "music player": "spotify",
    "my music player": "spotify",
    "calculator app": "calculator",
    "the calculator": "calculator",
    "my files": "explorer",
    "files": "explorer",
    "my folders": "explorer",
    "folder": "explorer",
    "file manager": "explorer",
    "my task manager": "task manager",
    "the task manager": "task manager",
    "my settings": "settings",
    "the settings": "settings",
    "screenshot tool": "snipping tool",
    "my paint": "paint",
}

GENERIC_WEBSITE_PHRASES: dict[str, str] = {
    "my email": "gmail",
    "email": "gmail",
    "my mail": "gmail",
    "my inbox": "gmail",
    "my drive": "google drive",
    "drive": "google drive",
    "my google drive": "google drive",
    "docs": "google docs",
    "my docs": "google docs",
    "the chat": "chatgpt",
    "my youtube": "youtube",
}

# Shells and terminal emulators. These are recognised so the assistant can
# answer deterministically, but they are deliberately NOT launchable: the
# project's safety rule is that no shell is ever started on the user's behalf.
SHELL_NAMES = frozenset(
    {
        "terminal",
        "the terminal",
        "my terminal",
        "windows terminal",
        "command prompt",
        "cmd",
        "the command prompt",
        "powershell",
        "powershell.exe",
        "windows powershell",
        "pwsh",
        "shell",
        "console",
        "bash",
        "wsl",
    }
)

# Folders whose name could plausibly be an app ("music") are only treated as
# folders when the user clearly means a folder ("... folder") or when the name
# is unambiguous.
_PLAIN_FOLDERS = frozenset(
    {"downloads", "documents", "desktop", "pictures", "videos", "home"}
)


# ---------------------------------------------------------------------------
# COMMANDS -- fixed phrases, no variables
# ---------------------------------------------------------------------------
# These are recognised with an exact lookup after normalisation, so they are
# instant and cannot be confused by the regex patterns.

COMMANDS: dict[str, list[str]] = {
    # -- Obsidian: list notes ------------------------------------------ 31 ---
    OBSIDIAN_LIST: [
        "list my notes",
        "list notes",
        "list all notes",
        "list all my notes",
        "list my obsidian notes",
        "list my notes in obsidian",
        "list my vault",
        "list my obsidian vault",
        "show my notes",
        "show notes",
        "show all notes",
        "show all my notes",
        "show me my notes",
        "show me all my notes",
        "show my obsidian notes",
        "show me my obsidian notes",
        "show my notes in obsidian",
        "show my vault",
        "show me my vault",
        "show my obsidian vault",
        "show me everything in my vault",
        "what notes do i have",
        "what notes do i have in my vault",
        "what notes are in my vault",
        "what is in my vault",
        "what's in my vault",
        "which notes do i have",
        "how many notes do i have",
        "do i have any notes",
        "browse my notes",
        "browse my vault",
    ],
    # -- Help ---------------------------------------------------------- 23 ---
    HELP: [
        "help",
        "help me",
        "show help",
        "get help",
        "what can you do",
        "what can you do for me",
        "what commands do you support",
        "what commands do you have",
        "show commands",
        "list commands",
        "show me your commands",
        "what can i ask you",
        "what can i ask",
        "what can i say",
        "how can you help me",
        "how can you help",
        "what are your capabilities",
        "what are you capable of",
        "give me examples",
        "show me examples",
        "give me some examples",
        "what are the commands",
        "what are the available commands",
    ],
    # -- Status -------------------------------------------------------- 16 ---
    STATUS: [
        "status",
        "system status",
        "show status",
        "check status",
        "check the system",
        "check everything",
        "system check",
        "run a system check",
        "are you working",
        "are you online",
        "are you ok",
        "are you okay",
        "are you there",
        "how are things",
        "what is your status",
        "what's your status",
    ],
    # -- Ollama -------------------------------------------------------- 15 ---
    OLLAMA_STATUS: [
        "check ollama",
        "is ollama running",
        "is ollama up",
        "ollama status",
        "ollama running",
        "check the ollama server",
        "check my ollama server",
        "check ai server",
        "check the ai server",
        "is the ai server running",
        "is the ai server up",
        "is the llm running",
        "check the model server",
        "is the ollama server up",
        "ollama status check",
    ],
    # -- Model information --------------------------------------------- 13 ---
    MODEL_INFO: [
        "what model are you using",
        "which model are you using",
        "what model is this",
        "which model is this",
        "show current model",
        "show the current model",
        "what is the current model",
        "what's the current model",
        "tell me the current model",
        "what ai model are you using",
        "which ai model are you using",
        "what ai model is this",
        "model info",
    ],
    # -- Voice: turn voice mode on -------------------------------------- 14 ---
    VOICE_ON: [
        "start listening",
        "listen",
        "start voice mode",
        "enable voice mode",
        "switch to voice mode",
        "use voice mode",
        "turn on voice mode",
        "voice mode on",
        "enable voice",
        "turn on voice",
        "start voice input",
        "voice on",
        "listen to me",
        "start voice",
    ],
    # -- Voice: turn voice mode off ------------------------------------- 15 ---
    VOICE_OFF: [
        "stop listening",
        "stop voice",
        "stop voice mode",
        "disable voice mode",
        "switch to text mode",
        "use text mode",
        "turn off voice mode",
        "voice mode off",
        "disable voice",
        "turn off voice",
        "text mode",
        "voice off",
        "switch off voice mode",
        "stop voice input",
        "no more voice",
    ],
    # -- Repetition ----------------------------------------------------- 13 ---
    REPEAT: [
        "repeat that",
        "repeat that please",
        "say that again",
        "say it again",
        "say that once more",
        "repeat your answer",
        "repeat the last answer",
        "read that again",
        "repeat",
        "repeat please",
        "what did you say",
        "can you repeat that",
        "come again",
    ],
    # -- Stop speaking -------------------------------------------------- 11 ---
    SPEAK_STOP: [
        "stop speaking",
        "stop talking",
        "stop the speech",
        "stop reading",
        "be quiet",
        "quiet",
        "silence",
        "cancel speech",
        "can you stop talking",
        "don't speak",
        "dont speak",
    ],
    # -- Conversation reset --------------------------------------------- 17 ---
    CLEAR_CHAT: [
        "clear chat",
        "clear the chat",
        "clear conversation",
        "clear the conversation",
        "clear this conversation",
        "clear our conversation",
        "clear history",
        "new chat",
        "new conversation",
        "start a new conversation",
        "start a fresh conversation",
        "reset chat",
        "reset conversation",
        "restart conversation",
        "reset",
        "start over",
        "forget the conversation",
    ],
    # -- Cancellation --------------------------------------------------- 16 ---
    CANCEL: [
        "cancel",
        "cancel that",
        "never mind",
        "nevermind",
        "forget it",
        "forget that",
        "forget about it",
        "abort",
        "stop",
        "stop it",
        "leave it",
        "skip that",
        "don't do that",
        "dont do that",
        "no thanks",
        "no thank you",
    ],
    # -- Greetings ------------------------------------------------------ 16 ---
    GREETING: [
        "hello",
        "hi",
        "hey",
        "yo",
        "howdy",
        "greetings",
        "hi there",
        "hello there",
        "hey there",
        "hey assistant",
        "hello assistant",
        "hi assistant",
        "good morning",
        "good afternoon",
        "good evening",
        "morning",
    ],
    # -- Thanks --------------------------------------------------------- 11 ---
    THANKS: [
        "thank you",
        "thanks",
        "thanks a lot",
        "thank you so much",
        "thank you very much",
        "thanks for that",
        "thanks assistant",
        "ty",
        "cheers",
        "appreciate it",
        "much appreciated",
    ],
    # -- Goodbye -------------------------------------------------------- 16 ---
    GOODBYE: [
        "goodbye",
        "good bye",
        "bye",
        "bye bye",
        "see you",
        "see ya",
        "see you later",
        "talk to you later",
        "catch you later",
        "exit",
        "quit",
        "good night",
        "i'm done",
        "im done",
        "that's all",
        "thats all",
    ],
    # -- Shells / terminals: recognised, but never launched ------------- 12 ---
    SHELL_BLOCKED: [
        "open terminal",
        "open the terminal",
        "open a terminal",
        "open my terminal",
        "open windows terminal",
        "open command prompt",
        "open the command prompt",
        "open cmd",
        "open powershell",
        "open windows powershell",
        "open shell",
        "open bash",
    ],
}

# ---------------------------------------------------------------------------
# Developer / testing phrases  (DIAGNOSTIC)
# ---------------------------------------------------------------------------
# phrase -> component name. core.py answers each one with a safe readiness
# report built from code that already exists; nothing is launched or modified.

DIAGNOSTIC_COMMANDS: dict[str, str] = {
    "test ollama": "ollama",
    "test the ai": "ollama",
    "test ai": "ollama",
    "test the model": "model",
    "test connection": "backend",
    "test the connection": "backend",
    "test backend": "backend",
    "test the backend": "backend",
    "run diagnostics": "backend",
    "run a diagnostic": "backend",
    "diagnostics": "backend",
    "test microphone": "microphone",
    "test the microphone": "microphone",
    "test mic": "microphone",
    "test voice": "voice",
    "test the voice": "voice",
    "test voice input": "voice",
    "test speech recognition": "stt",
    "test stt": "stt",
    "test speaker": "speaker",
    "test the speaker": "speaker",
    "test text to speech": "speaker",
    "test tts": "speaker",
    "test obsidian": "obsidian",
    "test the vault": "obsidian",
    "test my vault": "obsidian",
    "test google search": "browser",
    "test the browser": "browser",
    "test app launcher": "apps",
    "test the app launcher": "apps",
    "test apps": "apps",
}

# ---------------------------------------------------------------------------
# Append phrases that name no note
# ---------------------------------------------------------------------------
# These are real append requests with a missing note name, so core.py can ask
# "Which note do you mean?" instead of guessing or creating a new note.

NO_NOTE_APPEND_PHRASES: list[str] = [
    "add this to my obsidian note",
    "append this to my obsidian note",
    "add this to obsidian",
    "append this to obsidian",
    "save this in obsidian",
    "save this to obsidian",
    "add this to my note",
    "append this to my note",
    "save this to my note",
    "save this in my note",
    "put this in my note",
    "write this to my note",
    "add to my notes",
    "append to my notes",
]


# ---------------------------------------------------------------------------
# COMMAND_PATTERNS -- phrases with a variable part
# ---------------------------------------------------------------------------
# Each pattern is anchored (^...$) and uses one of the named groups:
#   (?P<q>...)       search query
#   (?P<name>...)    new note name
#   (?P<note>...)    existing note name
#   (?P<content>...) text to write into a note
# Patterns are tried in the order they appear in _PATTERN_ORDER, so notes are
# always matched before a generic web search.

# "append this to my X note", "add to my X note", "put this in my X note"...
_APPEND_LEAD = (
    _APPEND_VERBS
    + r"\s+"
    + r"(?:(?:this|that|it|the\s+following|the\s+text|the\s+above|"
    + r"this\s+information|this\s+text|this\s+note|the\s+note)\s+)?"
    + r"(?:to|in|into|onto|at)\s+"
    + r"(?:my\s+|the\s+|your\s+)?"
)
# A separator makes everything after it the content.
_CONTENT_REQUIRED = r"\s*(?:[:,-]|\bthat\s+says?\b|\bwith\s+(?:content|text)\b)\s*(?P<content>.+?)"

COMMAND_PATTERNS: dict[str, list[str]] = {
    # -- Obsidian: create a note --------------------------------------- 6 ---
    OBSIDIAN_CREATE: [
        # "create a note called X [with content Y]"
        _F + _CREATE_VERBS + r"\s+" + _ART + _NOTE_WORD + _LABEL + _NAME + _CONTENT + r"$",
        # "create X note [content Y]" (never "add this to my X note": that is an
        # append, and the append patterns are tried first)
        _F + _CREATE_VERBS + r"\s+" + _ART + r"(?!(?:this|that|it|them)\b)"
        + _NAME + r"\s+note" + _CONTENT + r"$",
        # "create the note X"
        _F + _CREATE_VERBS + r"\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:obsidian\s+)?note\s+"
        + _LABEL + _NAME + _CONTENT + r"$",
        # "make a note about X"
        _F + _CREATE_VERBS + r"\s+" + _ART + r"note\s+(?:about|on|for|regarding|"
        + r"covering|documenting)\s+" + _NAME + _CONTENT + r"$",
        # "create a new note in obsidian called X"
        _F + _CREATE_VERBS + r"\s+" + _ART + r"note\s+in\s+(?:my\s+|the\s+)?obsidian\s+"
        + _LABEL + _NAME + _CONTENT + r"$",
        # "start a note for X"
        _F + _CREATE_VERBS + r"\s+" + _ART + _NOTE_WORD + r"\s+for\s+" + _NAME + _CONTENT + r"$",
    ],
    # -- Obsidian: append to a note ------------------------------------ 5 ---
    OBSIDIAN_APPEND: [
        # "append this to my X note: Y"
        _F + _APPEND_LEAD + _NOTE_NAME + r"\s+note" + _CONTENT + r"$",
        # "append this to my note called X: Y"
        _F + _APPEND_LEAD + r"note\s+(?:called|named|titled)\s+" + _NOTE_NAME + _CONTENT + r"$",
        # "save this to X: Y"  (content is required here so "my note" is not eaten)
        _F + _APPEND_LEAD + _NOTE_NAME + _CONTENT_REQUIRED + r"$",
        # "add this to my X note that says Y"
        _F + _APPEND_LEAD + _NOTE_NAME + r"\s+note\s+that\s+(?:says?|reads?)\s+(?P<content>.+)$",
        # "append this to my X note in obsidian: Y"
        _F + _APPEND_LEAD + _NOTE_NAME + r"\s+note\s+in\s+(?:my\s+|the\s+)?obsidian"
        + _CONTENT + r"$",
        # "add this to my X"  (no note word and no content: core asks for whatever
        # is missing, so this stays in last place and is deliberately broad)
        _F + _APPEND_LEAD + _NOTE_NAME + r"\s*$",
    ],
    # -- Obsidian: search the vault ------------------------------------ 8 ---
    OBSIDIAN_SEARCH: [
        # "search my notes for X", "search for my obsidian notes about X"
        _F + _SEARCH_VERBS + r"\s+(?:me\s+)?(?:(?:in|through|inside|across|for)\s+)?\s*"
        + _SCOPE + r"\s+" + _REL + r"\s+" + _QUERY + r"$",
        # "find information about X in my notes"
        _F + _SEARCH_VERBS + r"\s+(?:me\s+)?(?:for\s+)?" + _INFO + _REL + r"\s+"
        + _QUERY + r"\s+(?:in|from|inside|within)\s+" + _SCOPE + r"$",
        # "find X in my notes", "look for X in my vault", "search for X in my notes"
        _F + _SEARCH_VERBS + r"\s+(?:me\s+)?(?:for\s+)?" + _INFO + _QUERY
        + r"\s+(?:in|from|inside|within)\s+" + _SCOPE + r"$",
        # "notes about X"
        _F + _SCOPE + r"\s+" + _REL + r"\s+" + _QUERY + r"$",
        # "do I have any notes about X"
        _F + r"(?:do|are)\s+(?:i|there)\s+have\s+(?:any\s+)?" + _SCOPE + r"\s+" + _REL
        + r"\s+" + _QUERY + r"$",
        # "what do my notes say about X"
        _F + r"what\s+do\s+(?:my\s+|the\s+)?" + _SCOPE + r"\s+(?:say|have|contain)\s+"
        + _REL + r"\s+" + _QUERY + r"$",
        # "read my notes about X"
        _F + _SEARCH_VERBS + r"\s+(?:me\s+)?(?:my\s+)?" + _NOTE_WORD + r"\s+" + _REL
        + r"\s+" + _QUERY + r"$",
        # "search my notes" (no query yet -> core asks for one)
        _F + _SEARCH_VERBS + r"\s+(?:me\s+)?(?:(?:in|through|inside)\s+)?" + _SCOPE + r"\s*$",
    ],
    # -- Obsidian: read one note --------------------------------------- 6 ---
    OBSIDIAN_READ: [
        # "read my note called X"
        _F + _READ_VERBS + r"\s+(?:me\s+)?(?:my\s+|the\s+|your\s+)?(?:obsidian\s+)?"
        + _NOTE_WORD + r"\s+(?:called|named|titled|labelled|labeled)\s*[:,-]?\s*"
        + _NOTE_NAME + r"\s*$",
        # "read my Python note", "open my Investment Ideas note"
        _F + _READ_VERBS + r"\s+(?:me\s+)?(?:my\s+|the\s+|your\s+)?(?:obsidian\s+)?"
        + _NOTE_NAME + r"\s+note\s*$",
        # "read my note X"
        _F + _READ_VERBS + r"\s+(?:me\s+)?(?:my\s+|the\s+|your\s+)?note\s+" + _NOTE_NAME + r"\s*$",
        # "read X from Obsidian"
        _F + _READ_VERBS + r"\s+(?:me\s+)?(?:my\s+|the\s+|your\s+)?(?:obsidian\s+)?"
        + _NOTE_NAME + r"\s+(?:from|in|out\s+of)\s+(?:my\s+|the\s+)?obsidian\s*$",
        # "what's in my Python note"
        _F + r"(?:what(?:'s|\s+is)\s+in|what\s+does)\s+(?:my\s+|the\s+)?"
        + _NOTE_NAME + r"\s+note(?:\s+say)?\s*$",
        # "read the file X"
        _F + _READ_VERBS + r"\s+(?:me\s+)?(?:my\s+|the\s+|your\s+)?(?:obsidian\s+)?file\s+"
        + r"(?:called|named)?\s*" + _NOTE_NAME + r"\s*$",
    ],
    # -- Web search (Google is the engine) ----------------------------- 36 ---
    GOOGLE_SEARCH: [
        # "search google for X" / "search google X" / "search on google for X"
        _F + r"search\s+google\s+for\s+" + _QUERY + r"$",
        _F + r"search\s+google\s+" + _NOT_NOTES + _QUERY + r"$",
        _F + r"search\s+on\s+google\s+for\s+" + _QUERY + r"$",
        _F + r"search\s+on\s+google\s+" + _NOT_NOTES + _QUERY + r"$",
        # "google search for X" / "google search X"
        _F + r"google\s+search\s+for\s+" + _QUERY + r"$",
        _F + r"google\s+search\s+" + _NOT_NOTES + _QUERY + r"$",
        _F + r"do\s+a\s+google\s+search\s+(?:for\s+)?" + _QUERY + r"$",
        _F + r"run\s+a\s+google\s+search\s+(?:for\s+)?" + _QUERY + r"$",
        _F + r"do\s+a\s+search\s+(?:for\s+)?" + _QUERY + r"$",
        # "google X" / "google it X"
        _F + r"google\s+" + _NOT_NOTES + _QUERY + r"$",
        _F + r"google\s+(?:it|this|that)\s+" + _QUERY + r"$",
        # "search the web for X", "search online for X", "web search for X"
        _F + r"search\s+the\s+(?:web|internet)\s+(?:for\s+)?" + _QUERY + r"$",
        _F + r"search\s+(?:the\s+)?web\s+for\s+" + _QUERY + r"$",
        _F + r"search\s+online\s+(?:for\s+)?" + _QUERY + r"$",
        _F + r"web\s+search\s+(?:for\s+)?" + _QUERY + r"$",
        _F + r"search\s+" + _NOT_NOTES + r"(?:for\s+)?" + _QUERY + r"\s+online$",
        _F + r"search\s+for\s+" + _NOT_NOTES + _QUERY + r"$",
        _F + r"search\s+" + _NOT_NOTES + _QUERY + r"$",
        # "look up X" / "look this up" / "look online for X"
        _F + r"look\s+up\s+" + _NOT_NOTES + _QUERY + r"$",
        _F + r"look\s+(?:this|that|it)\s+up\s+" + _QUERY + r"$",
        _F + r"look\s+(?:this|that|it)\s+up\s*$",
        _F + r"look\s+" + _QUERY + r"\s+up\s+online$",
        _F + r"look\s+online\s+for\s+" + _QUERY + r"$",
        _F + r"look\s+(?:online|on\s+the\s+(?:web|internet))\s+for\s+" + _QUERY + r"$",
        _F + r"look\s+for\s+" + _QUERY + r"\s+(?:online|on\s+the\s+(?:web|internet))$",
        # "find X on google" / "find information about X" / "find X online"
        _F + r"find\s+" + _QUERY + r"\s+on\s+google$",
        _F + r"find\s+" + _QUERY + r"\s+on\s+the\s+(?:web|internet)$",
        _F + r"find\s+(?:this|that|it)\s+on\s+the\s+(?:web|internet)\s+" + _QUERY + r"$",
        _F + r"find\s+information\s+(?:about|on)\s+" + _QUERY + r"$",
        _F + r"find\s+info\s+(?:about|on)\s+" + _QUERY + r"$",
        _F + r"find\s+out\s+about\s+" + _QUERY + r"$",
        _F + r"find\s+" + _QUERY + r"\s+online$",
        # "check google for X" / "what does google say about X"
        _F + r"check\s+google\s+for\s+" + _QUERY + r"$",
        _F + r"what\s+does\s+google\s+say\s+about\s+" + _QUERY + r"$",
        _F + r"search\s+(?:it|this|that)\s+(?:on\s+google|online|on\s+the\s+(?:web|internet))\s+"
        + _QUERY + r"$",
    ],
}


# ---------------------------------------------------------------------------
# OPEN_APP / OPEN_WEBSITE / OPEN_FOLDER -- every verb x every name
# ---------------------------------------------------------------------------
# Instead of writing the phrases out by hand, one verb list is combined with the
# name tables in tools.py. That covers, for example:
#     open chrome / launch chrome / start chrome / run chrome / bring up chrome
#     go to chrome / visit chrome / take me to chrome / show me chrome ...
# for every app, and the same for websites and folders.
#
# Adding an app in tools.APP_ALIASES automatically adds all of these phrases.

APP_VERBS = [
    "open",
    "launch",
    "start",
    "run",
    "bring up",
    "pull up",
    "fire up",
    "go to",
    "visit",
    "take me to",
    "navigate to",
    "jump to",
    "show me",
    "switch to",
]

WEBSITE_VERBS = [
    "open",
    "launch",
    "start",
    "go to",
    "visit",
    "take me to",
    "navigate to",
    "show me",
]

FOLDER_VERBS = ["open", "launch", "show me", "go to"]

COMMANDS[OPEN_APP] = [
    f"{verb} {name}" for verb in APP_VERBS for name in sorted(APP_ALIASES)
]
COMMANDS[OPEN_APP] += [
    f"{verb} {phrase}" for verb in APP_VERBS for phrase in sorted(GENERIC_APP_PHRASES)
]
COMMANDS[OPEN_WEBSITE] = [
    f"{verb} {name}" for verb in WEBSITE_VERBS for name in sorted(WEBSITES)
]
COMMANDS[OPEN_WEBSITE] += [
    f"{verb} {phrase}"
    for verb in WEBSITE_VERBS
    for phrase in sorted(GENERIC_WEBSITE_PHRASES)
]

# "music" can also mean the Spotify app, so only unambiguous folder names get the
# short form; every folder name works with an explicit "... folder".
_PLAIN_FOLDER_NAMES = sorted(name for name in FOLDERS if name in _PLAIN_FOLDERS)
_ALL_FOLDER_NAMES = sorted(FOLDERS)

COMMANDS[OPEN_FOLDER] = [
    f"{verb} {name}" for verb in FOLDER_VERBS for name in _PLAIN_FOLDER_NAMES
]
COMMANDS[OPEN_FOLDER] += [
    f"{verb} my {name}" for verb in FOLDER_VERBS for name in _PLAIN_FOLDER_NAMES
]
COMMANDS[OPEN_FOLDER] += [
    f"{verb} {name} folder" for verb in FOLDER_VERBS for name in _ALL_FOLDER_NAMES
]
COMMANDS[OPEN_FOLDER] += [
    f"{verb} my {name} folder" for verb in FOLDER_VERBS for name in _ALL_FOLDER_NAMES
]


# ---------------------------------------------------------------------------
# Target resolution -- apps, websites, folders, shells
# ---------------------------------------------------------------------------

_TARGET_LEAD = re.compile(r"^(?:my|the|a|an|your|our)\s+")
_TARGET_TAIL = re.compile(
    r"\s+(?:app|application|program|website|site|page|folder|directory)$"
)
_FOLDER_HINT = re.compile(r"\b(?:folder|directory)\b")
# Fallback for verb+name combinations that are not in the exact table, e.g.
# "can you bring up my code editor".
_OPEN_TARGET = re.compile(
    _F
    + _OPEN_VERBS
    + r"\s+(?:(?:the|my|a|an|your)\s+)?"
    + r"(?:(?:app|application|program|website|site)\s+)?"
    + r"(?P<target>[a-z0-9 ._+'\-]{1,60}?)\s*$",
    re.IGNORECASE,
)


def target_forms(target: str) -> tuple[str, str]:
    """Return the (as written, cleaned) forms of a target name."""
    raw = squeeze(target).lower()
    base = _TARGET_LEAD.sub("", raw)
    base = _TARGET_TAIL.sub("", base).strip()
    return raw, base


def resolve_target(target: str) -> Match | None:
    """Map a name onto OPEN_APP / OPEN_WEBSITE / OPEN_FOLDER / SHELL_BLOCKED.

    Only names that already exist in the fixed tables can match, so no user text
    can ever become an executable path or a command.
    """
    raw, base = target_forms(target)
    if not base:
        return None
    for form in (raw, base):
        if form in APP_ALIASES:
            return Match(OPEN_APP, form)
    folder_hint = bool(_FOLDER_HINT.search(raw))
    if base in FOLDERS and (folder_hint or base in _PLAIN_FOLDERS):
        return Match(OPEN_FOLDER, base)
    if base in GENERIC_APP_PHRASES:
        return Match(OPEN_APP, GENERIC_APP_PHRASES[base])
    if base in WEBSITES:
        return Match(OPEN_WEBSITE, base)
    if base in GENERIC_WEBSITE_PHRASES:
        return Match(OPEN_WEBSITE, GENERIC_WEBSITE_PHRASES[base])
    if base in FOLDERS:
        return Match(OPEN_FOLDER, base)
    if base in SHELL_NAMES:
        return Match(SHELL_BLOCKED, base)
    return None


def _resolve_open_request(text: str) -> Match | None:
    """``"can you bring up my code editor"`` -> ``OPEN_APP / vs code``."""
    found = _OPEN_TARGET.match(text)
    if not found:
        return None
    return resolve_target(found.group("target"))


# ---------------------------------------------------------------------------
# Argument cleaning
# ---------------------------------------------------------------------------

# Names that mean "no name was given": core.py then asks which note.
_NOTE_PLACEHOLDERS = frozenset(
    {
        "note",
        "notes",
        "my note",
        "my notes",
        "the note",
        "the notes",
        "a note",
        "obsidian",
        "my obsidian",
        "file",
        "my file",
        "the file",
        "vault",
        "my vault",
        "it",
        "this",
        "that",
        "quick note",
    }
)

_EMPTY_QUERIES = frozenset(
    {"", "it", "this", "that", "them", "something", "anything"}
)


def _clean_note(value: str | None) -> str:
    name = squeeze(value or "").strip("\"'").strip()
    if name.lower().rstrip(".") in _NOTE_PLACEHOLDERS:
        return ""
    return name


def _clean_query(value: str | None) -> str:
    query = squeeze(value or "").strip("\"'").strip()
    if query.lower().rstrip("?.!") in _EMPTY_QUERIES:
        return ""
    return query


def _clean_content(value: str | None) -> str:
    return squeeze(value or "").strip("\"'").strip()


def _build_match(intent: str, found: "re.Match") -> Match:
    """Turn a regex match into a Match, cleaning the captured arguments."""
    groups = found.groupdict()
    if intent == OBSIDIAN_CREATE:
        return Match(
            intent, _clean_note(groups.get("name")), _clean_content(groups.get("content"))
        )
    if intent == OBSIDIAN_APPEND:
        return Match(
            intent, _clean_note(groups.get("note")), _clean_content(groups.get("content"))
        )
    if intent == OBSIDIAN_READ:
        return Match(intent, _clean_note(groups.get("note")), "")
    return Match(intent, _clean_query(groups.get("q")), "")


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------
# Notes are checked before web search, which is the only place a generic
# "search ..." pattern exists. Apps/websites/folders are checked in between, so
# "open chrome" can never be mistaken for a Google search.
#
# Append comes before create because "add this to my X note" starts with a create
# verb ("add") but is an append; the append patterns all require a preposition.

_NOTE_PATTERNS = [
    (intent, re.compile(pattern, re.IGNORECASE))
    for intent in (OBSIDIAN_APPEND, OBSIDIAN_CREATE, OBSIDIAN_SEARCH, OBSIDIAN_READ)
    for pattern in COMMAND_PATTERNS[intent]
]
_WEB_PATTERNS = [
    (GOOGLE_SEARCH, re.compile(pattern, re.IGNORECASE))
    for pattern in COMMAND_PATTERNS[GOOGLE_SEARCH]
]

# The exact lookup needs a lower-cased key, but the patterns must keep the
# original capitalisation so note names and search queries survive intact
# ("Investment Analysis" must not become "investment analysis").
_OPEN_INTENTS = frozenset({OPEN_APP, OPEN_WEBSITE, OPEN_FOLDER})
_ALL_VERBS = tuple(
    sorted({*APP_VERBS, *WEBSITE_VERBS, *FOLDER_VERBS}, key=len, reverse=True)
)


def _strip_open_verb(phrase: str) -> str:
    """``"launch my code editor"`` -> ``"my code editor"``."""
    lowered = phrase.lower()
    for verb in _ALL_VERBS:
        if lowered.startswith(verb + " "):
            return phrase[len(verb) + 1 :]
    return phrase


def _build_exact_index() -> dict[str, Match]:
    """phrase -> Match. The first definition wins, so COMMANDS can override."""
    index: dict[str, Match] = {}
    for intent, phrases in COMMANDS.items():
        for phrase in phrases:
            key = normalize(phrase)
            if not key:
                continue
            if intent in _OPEN_INTENTS:
                # "go to my code editor" must carry the resolved target, so the
                # value is worked out here instead of being left empty.
                resolved = resolve_target(_strip_open_verb(key))
                if resolved is None:
                    continue
                index.setdefault(key, resolved)
            else:
                index.setdefault(key, Match(intent))
    for phrase, component in DIAGNOSTIC_COMMANDS.items():
        index.setdefault(normalize(phrase), Match(DIAGNOSTIC, component))
    for phrase in NO_NOTE_APPEND_PHRASES:
        index.setdefault(normalize(phrase), Match(OBSIDIAN_APPEND, ""))
    return index


EXACT_COMMANDS: dict[str, Match] = _build_exact_index()


def recognize(text: str) -> Match | None:
    """Return the command a sentence means, or None (which means: ask Ollama).

    Pure and deterministic: no I/O, no side effects, no execution.
    """
    normalized = normalize(text)
    if not normalized:
        return None
    # Whitespace-collapsed but case-preserving, used for the regex patterns.
    spoken = squeeze(text)

    exact = EXACT_COMMANDS.get(normalized)
    if exact is not None:
        return exact

    for intent, pattern in _NOTE_PATTERNS:
        found = pattern.match(spoken)
        if found:
            return _build_match(intent, found)

    target = resolve_target(normalized) or _resolve_open_request(normalized)
    if target is not None:
        return target

    for intent, pattern in _WEB_PATTERNS:
        found = pattern.match(spoken)
        if found:
            return _build_match(intent, found)

    return None


# ---------------------------------------------------------------------------
# Vocabulary size (handy when editing this file)
# ---------------------------------------------------------------------------


def vocabulary_report() -> dict[str, int]:
    """How many phrases exist per intent."""
    report = {intent: len(phrases) for intent, phrases in COMMANDS.items()}
    for intent, patterns in COMMAND_PATTERNS.items():
        report[f"{intent} (patterns)"] = len(patterns)
    report["DIAGNOSTIC"] = len(DIAGNOSTIC_COMMANDS)
    report["OBSIDIAN_APPEND (no note name)"] = len(NO_NOTE_APPEND_PHRASES)
    return report


def total_phrases() -> int:
    """Total number of recognisable phrases in this vocabulary."""
    return (
        sum(len(phrases) for phrases in COMMANDS.values())
        + sum(len(patterns) for patterns in COMMAND_PATTERNS.values())
        + len(DIAGNOSTIC_COMMANDS)
        + len(NO_NOTE_APPEND_PHRASES)
    )


TOTAL_PHRASES = total_phrases()

