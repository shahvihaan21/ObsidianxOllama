"""Controlled Windows tools: launching apps, Google search, Obsidian notes.

Nothing here accepts a shell string. Application launching is limited to the
alias table below, so text from the user or the model can never reach a command
interpreter. There is no ``os.system`` and no ``shell=True`` anywhere.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.parse
import webbrowser

from obsidian import NOT_CONFIGURED, Obsidian, ObsidianError, format_results

GOOGLE_SEARCH_URL = "https://www.google.com/search?q={query}"

# Friendly name -> (executable or URI protocol, extra arguments).
# Shells and script hosts (cmd, powershell, wscript...) are deliberately absent:
# they are not launchable through this tool.
APP_ALIASES: dict[str, tuple[str, list[str]]] = {
    "chrome": ("chrome.exe", []),
    "google chrome": ("chrome.exe", []),
    "edge": ("msedge.exe", []),
    "microsoft edge": ("msedge.exe", []),
    "firefox": ("firefox.exe", []),
    "notepad": ("notepad.exe", []),
    "wordpad": ("write.exe", []),
    "calculator": ("calc.exe", []),
    "calc": ("calc.exe", []),
    "paint": ("mspaint.exe", []),
    "explorer": ("explorer.exe", []),
    "file explorer": ("explorer.exe", []),
    "task manager": ("taskmgr.exe", []),
    "settings": ("ms-settings:", []),
    "snipping tool": ("snippingtool.exe", []),
    "vs code": ("code.cmd", []),
    "vscode": ("code.cmd", []),
    "visual studio code": ("code.cmd", []),
    "obsidian": ("obsidian.exe", []),
    "spotify": ("spotify.exe", []),
    "discord": ("discord.exe", []),
    "vlc": ("vlc.exe", []),
    "7-zip": ("7zFM.exe", []),
    "excel": ("excel.exe", []),
    "word": ("winword.exe", []),
    "powerpoint": ("powerpnt.exe", []),
    "outlook": ("outlook.exe", []),
    "whatsapp": ("whatsapp.exe", []),
    "steam": ("steam.exe", []),
}

_DISPLAY_NAMES = {
    "chrome": "Chrome",
    "google chrome": "Google Chrome",
    "edge": "Edge",
    "microsoft edge": "Microsoft Edge",
    "firefox": "Firefox",
    "notepad": "Notepad",
    "wordpad": "WordPad",
    "calculator": "Calculator",
    "calc": "Calculator",
    "paint": "Paint",
    "explorer": "File Explorer",
    "file explorer": "File Explorer",
    "task manager": "Task Manager",
    "snipping tool": "Snipping Tool",
    "vs code": "VS Code",
    "vscode": "VS Code",
    "visual studio code": "VS Code",
    "7-zip": "7-Zip",
}

# Fallback install locations for apps that are usually not on PATH.
_KNOWN_PATHS: dict[str, list[str]] = {
    "chrome.exe": [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    ],
    "msedge.exe": [
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    ],
    "firefox.exe": [
        r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
        r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
    ],
    "code.cmd": [
        r"%LocalAppData%\Programs\Microsoft VS Code\bin\code.cmd",
        r"%ProgramFiles%\Microsoft VS Code\bin\code.cmd",
    ],
    "obsidian.exe": [
        r"%LocalAppData%\Obsidian\Obsidian.exe",
        r"%ProgramFiles%\Obsidian\Obsidian.exe",
    ],
    "spotify.exe": [r"%AppData%\Spotify\Spotify.exe"],
    "winword.exe": [r"%ProgramFiles%\Microsoft Office\root\Office16\WINWORD.EXE"],
    "excel.exe": [r"%ProgramFiles%\Microsoft Office\root\Office16\EXCEL.EXE"],
    "powerpnt.exe": [r"%ProgramFiles%\Microsoft Office\root\Office16\POWERPNT.EXE"],
    "outlook.exe": [r"%ProgramFiles%\Microsoft Office\root\Office16\OUTLOOK.EXE"],
    "7zFM.exe": [
        r"%ProgramFiles%\7-Zip\7zFM.exe",
        r"%ProgramFiles(x86)%\7-Zip\7zFM.exe",
    ],
}


def normalize_app_name(name: str) -> str:
    """'  Chrome.EXE ' -> 'chrome'."""
    key = " ".join(str(name or "").strip().lower().split())
    if key.endswith(".exe"):
        key = key[:-4]
    return key


def resolve_app(name: str) -> tuple[str, list[str]] | None:
    """Return (executable, args) for a known app, else None."""
    return APP_ALIASES.get(normalize_app_name(name))


def is_known_app(name: str) -> bool:
    return normalize_app_name(name) in APP_ALIASES


def display_name(key: str) -> str:
    return _DISPLAY_NAMES.get(key, key.title())


def _find_executable(executable: str) -> str | None:
    """Locate an executable on PATH, then in the known install locations."""
    found = shutil.which(executable)
    if found:
        return found
    for template in _KNOWN_PATHS.get(executable.lower(), []):
        candidate = os.path.expandvars(template)
        if "%" in candidate:
            continue
        if os.path.isfile(candidate):
            return candidate
    return None


def _launch_command(command: list[str]) -> None:
    """Start an executable. Never a shell, always an argument list."""
    subprocess.Popen(
        command,
        shell=False,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _open_uri(uri: str) -> None:
    """Open a fixed URI protocol handler (e.g. ``ms-settings:``)."""
    starter = getattr(os, "startfile", None)
    if starter is None:
        raise OSError("os.startfile is only available on Windows")
    starter(uri)


def open_app(name: str) -> str:
    """Launch a known application. Unknown names never reach the OS."""
    key = normalize_app_name(name)
    entry = APP_ALIASES.get(key)
    if entry is None:
        return f"I couldn't find {str(name or '').strip() or 'that app'}."
    target, arguments = entry
    if target.endswith(":"):
        _open_uri(target)
        return f"Opening {display_name(key)}."
    executable = _find_executable(target)
    if executable is None:
        return f"I couldn't find {display_name(key)}."
    _launch_command([executable, *arguments])
    return f"Opening {display_name(key)}."


def google_search(query: str) -> str:
    """Open a Google search results page in the default browser."""
    searched = " ".join(str(query or "").split())
    if not searched:
        return "What should I search for?"
    url = GOOGLE_SEARCH_URL.format(query=urllib.parse.quote_plus(searched))
    if not webbrowser.open(url, new=2, autoraise=True):
        return "I couldn't open your web browser."
    return "Opening Google search."


class Tools:
    """The tool surface the assistant is allowed to call."""

    def __init__(self, obsidian: Obsidian | None = None) -> None:
        self.obsidian = obsidian if obsidian is not None else Obsidian()

    # -- apps and browser ------------------------------------------------

    def open_app(self, name: str) -> str:
        return open_app(name)

    def google_search(self, query: str) -> str:
        return google_search(query)

    def is_known_app(self, name: str) -> bool:
        return is_known_app(name)

    # -- obsidian --------------------------------------------------------

    def obsidian_search(self, query: str) -> str:
        return format_results(self._vault().search(query))

    def obsidian_read(self, note: str) -> str:
        return self._vault().read(note)

    def obsidian_create(self, note: str, content: str = "") -> str:
        return self._vault().create(note, content)

    def obsidian_append(self, note: str, content: str) -> str:
        return self._vault().append(note, content)

    def obsidian_exists(self, note: str) -> bool:
        return self._vault().exists(note)

    def obsidian_path(self, note: str) -> str:
        return self._vault().note_path_for(note)

    def _vault(self) -> Obsidian:
        if self.obsidian is None:
            raise ObsidianError(NOT_CONFIGURED)
        return self.obsidian
