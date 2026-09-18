"""Tool tests: app aliases, safe failures, and the Google search URL.

No app is launched, no browser is opened and nothing is installed.
"""

import pytest

from app import tools
from app.tools import (
    APP_ALIASES,
    Tools,
    google_search,
    is_known_app,
    normalize_app_name,
    open_app,
    resolve_app,
)


@pytest.fixture
def launcher(monkeypatch):
    """Capture launches instead of starting processes."""
    launched = []
    monkeypatch.setattr(tools, "_launch_command", launched.append)
    monkeypatch.setattr(tools, "_find_executable", lambda executable: f"C:/fake/{executable}")
    return launched


def test_aliases_resolve_to_executables():
    assert resolve_app("chrome") == ("chrome.exe", [])
    assert resolve_app("Chrome.EXE") == ("chrome.exe", [])
    assert resolve_app("  calculator  ") == ("calc.exe", [])
    assert resolve_app("calc") == ("calc.exe", [])
    assert resolve_app("vs code") == ("code.cmd", [])
    assert resolve_app("vscode") == ("code.cmd", [])
    assert resolve_app("notepad") == ("notepad.exe", [])
    assert resolve_app("explorer") == ("explorer.exe", [])
    assert normalize_app_name(" VS Code ") == "vs code"
    assert is_known_app("Chrome")
    assert not is_known_app("definitely-not-an-app")


def test_shells_are_not_launchable():
    for name in ("cmd", "command prompt", "powershell", "terminal", "windows terminal"):
        assert name not in APP_ALIASES
        assert not is_known_app(name)


def test_open_app_launches_the_expected_command(launcher):
    assert open_app("chrome") == "Opening Chrome."
    assert launcher == [["C:/fake/chrome.exe"]]


def test_unknown_app_fails_safely(launcher):
    assert open_app("definitely-not-an-app") == "I couldn't find definitely-not-an-app."
    assert launcher == []


def test_missing_executable_fails_safely(monkeypatch, launcher):
    monkeypatch.setattr(tools, "_find_executable", lambda executable: None)
    assert open_app("spotify") == "I couldn't find Spotify."
    assert launcher == []


@pytest.mark.parametrize(
    "hostile",
    [
        "notepad; del /f /q C:\\*",
        "chrome && shutdown /s",
        "chrome | powershell -c whoami",
        "..\\..\\evil.exe",
        "C:\\Windows\\System32\\cmd.exe",
        "powershell -EncodedCommand AAA",
    ],
)
def test_no_arbitrary_shell_execution(hostile, launcher):
    result = open_app(hostile)
    assert result.startswith("I couldn't find")
    assert launcher == []


def test_google_search_opens_the_expected_url(monkeypatch):
    opened = []

    def fake_open(url, **kwargs):
        opened.append((url, kwargs))
        return True

    monkeypatch.setattr(tools.webbrowser, "open", fake_open)
    assert google_search("Python internships") == "Opening Google search."
    assert opened[0][0] == "https://www.google.com/search?q=Python+internships"
    assert opened[0][1] == {"new": 2, "autoraise": True}


def test_google_search_encodes_special_characters(monkeypatch):
    opened = []
    monkeypatch.setattr(tools.webbrowser, "open", lambda url, **kwargs: opened.append(url) or True)
    google_search("ROCE & ROCE ratio")
    assert opened[0] == "https://www.google.com/search?q=ROCE+%26+ROCE+ratio"


def test_tools_wrapper_reuses_the_same_functions(launcher):
    toolset = Tools()
    assert toolset.is_known_app("notepad")
    assert toolset.open_app("notepad") == "Opening Notepad."
    assert launcher == [["C:/fake/notepad.exe"]]


# -- websites and folders (fixed tables, never user text) ---------------


def test_websites_open_fixed_urls(monkeypatch):
    opened = []
    monkeypatch.setattr(
        tools.webbrowser, "open", lambda url, **kwargs: opened.append(url) or True
    )
    assert tools.open_website("google") == "Opening Google."
    assert tools.open_website("Google Drive") == "Opening Google Drive."
    assert opened == ["https://www.google.com", "https://drive.google.com"]


def test_unknown_website_fails_safely(monkeypatch):
    opened = []
    monkeypatch.setattr(
        tools.webbrowser, "open", lambda url, **kwargs: opened.append(url) or True
    )
    assert "don't have a website" in tools.open_website("http://example.com")
    assert opened == []


def test_folders_resolve_inside_the_home_folder(monkeypatch):
    opened = []
    monkeypatch.setattr(tools, "_open_uri", opened.append)
    monkeypatch.setattr(tools.os.path, "isdir", lambda path: True)
    assert tools.open_folder("downloads") == "Opening your Downloads folder."
    assert len(opened) == 1
    assert opened[0].endswith("Downloads")


def test_unknown_folder_fails_safely():
    assert "couldn't find a folder" in tools.open_folder("nowhere")


def test_new_aliases_are_present():
    assert resolve_app("telegram") == ("telegram.exe", [])
    assert resolve_app("github desktop") == ("github.exe", [])
    assert "google" in tools.WEBSITES
    assert "downloads" in tools.FOLDERS
