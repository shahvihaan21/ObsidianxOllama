"""Application control: launch, close, focus.

Resolution order for an app name:
  1. an explicit entry in APP_ALIASES (handles friendly names like "vs code")
  2. an exact/prefix match against Start Menu shortcuts
  3. a PATH lookup (e.g. ``notepad.exe``)
  4. a direct execute of the raw string, if it is actually a file

Nothing here runs a shell, so an app name can never smuggle in a command.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from tools.registry import Level, Tool, ToolError

log = logging.getLogger(__name__)

# Friendly name -> (executable or protocol, extra args). Keep values executable,
# never a shell string.
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
    "cmd": ("cmd.exe", []),
    "command prompt": ("cmd.exe", []),
    "powershell": ("powershell.exe", []),
    "terminal": ("wt.exe", []),
    "windows terminal": ("wt.exe", []),
    "task manager": ("taskmgr.exe", []),
    "settings": ("ms-settings:", []),
    "snipping tool": ("snippingtool.exe", []),
    "vs code": ("code.cmd", []),
    "vscode": ("code.cmd", []),
    "code": ("code.cmd", []),
    "visual studio code": ("code.cmd", []),
    "spotify": ("spotify.exe", []),
    "obsidian": ("obsidian.exe", []),
    "discord": ("discord.exe", []),
    "vlc": ("vlc.exe", []),
    "7zip": ("7zFM.exe", []),
    "7-zip": ("7zFM.exe", []),
    "excel": ("excel.exe", []),
    "word": ("winword.exe", []),
    "powerpoint": ("powerpnt.exe", []),
    "outlook": ("outlook.exe", []),
    "whatsapp": ("whatsapp.exe", []),
    "steam": ("steam.exe", []),
}

# Directories that hold launchable shortcuts, in priority order.
_START_MENU_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

# Extra install locations worth probing for common apps when PATH misses them.
_EXTRA_DIRS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
    Path(os.environ.get("PROGRAMFILES", "")),
    Path(os.environ.get("PROGRAMFILES(X86)", "")),
]


class AppNotFound(ToolError):
    def __init__(self, name: str, tried: list[str]) -> None:
        detail = "; ".join(tried) if tried else "no candidates"
        super().__init__(
            f"Could not find an application called {name!r}. Tried: {detail}. "
            "Use the exact executable name, or an absolute path.",
            "app_not_found",
        )


def _resolve_app(name: str) -> tuple[str, list[str]]:
    """Resolve a friendly name to something launchable, without a shell."""
    key = name.strip().lower()
    key_no_ext = key[:-4] if key.endswith(".exe") else key
    tried: list[str] = []

    # 0. A real file path takes precedence -- the user was explicit.
    candidate_path = Path(name).expanduser()
    if candidate_path.is_file():
        return str(candidate_path), []

    # 1. Alias table.
    for lookup in (key, key_no_ext):
        if lookup in APP_ALIASES:
            exe, args = APP_ALIASES[lookup]
            resolved = shutil.which(exe)
            if resolved:
                return resolved, list(args)
            # URI protocols and apps we cannot resolve go straight to start.
            if exe.endswith(":"):
                return exe, list(args)
            tried.append(f"alias {lookup} -> {exe} (not on PATH)")

    # 2. PATH.
    for exe in (name, f"{name}.exe", f"{key_no_ext}.exe"):
        resolved = shutil.which(exe)
        if resolved:
            return resolved, []
        tried.append(f"PATH:{exe}")

    # 3. Start Menu shortcut (.lnk or .url).
    target_lower = key_no_ext
    for base in _START_MENU_DIRS:
        if not base.is_dir():
            continue
        for pattern in ("*.lnk", "*.url"):
            for shortcut in base.rglob(pattern):
                stem = shortcut.stem.lower()
                if stem == target_lower or stem.startswith(target_lower):
                    return str(shortcut), []

    # 4. Extra install directories, shallow scan for an .exe stem match.
    for base in _EXTRA_DIRS:
        if not base or not base.is_dir():
            continue
        try:
            for sub in base.iterdir():
                if not sub.is_dir():
                    continue
                if target_lower in sub.name.lower():
                    for exe in sub.glob("*.exe"):
                        if target_lower.replace(" ", "") in exe.stem.lower().replace(" ", ""):
                            return str(exe), []
        except (OSError, PermissionError):
            continue
        tried.append(f"dir:{base}")

    # 5. Give Windows' own resolver a chance for URI protocols.
    if name.endswith(":") or ":" in name and not Path(name).is_file():
        return name, []

    raise AppNotFound(name, tried)


def _spawn(target: str, args: list[str]) -> None:
    """Launch a target detached from this process."""
    # CREATE_NEW_PROCESS_GROUP + DETACHED so the app outlives the agent.
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    try:
        subprocess.Popen(
            [target, *args],
            shell=False,  # never a shell: no command injection from a name
            creationflags=flags,
            close_fds=True,
        )
    except OSError:
        # Fall back to os.startfile, which handles .lnk/.url and protocols.
        os.startfile(target)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------


def open_application(name: str, args: str = "") -> str:
    """Launch an application by friendly name."""
    target, base_args = _resolve_app(name)
    extra = [a for a in args.split()] if args else []
    _spawn(target, base_args + extra)
    time.sleep(0.6)  # give the window a moment to appear
    return f"{name} launched."


def close_application(name: str) -> str:
    """Terminate running processes whose name matches."""
    stem = name.strip().lower()
    if stem.endswith(".exe"):
        stem = stem[:-4]
    image = f"{stem}.exe"

    # Refuse to kill anything that would take down the desktop or the agent.
    protected = {
        "explorer", "csrss", "wininit", "winlogon", "services", "lsass",
        "smss", "system", "registry", "dwm", "python", "pythonw", "ollama",
    }
    if stem in protected:
        raise ToolError(
            f"Refusing to close {name!r}: it is a protected system or agent process.",
            "protected_process",
        )

    try:
        completed = subprocess.run(
            ["taskkill", "/IM", image],
            capture_output=True, text=True, timeout=15, shell=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ToolError(f"taskkill failed: {exc}") from exc

    if completed.returncode != 0:
        raise ToolError(
            f"{name} does not appear to be running.", "not_running"
        )
    return f"{name} closed."


def focus_application(title: str) -> str:
    """Bring a window to the foreground by title fragment."""
    try:
        import pygetwindow as gw
    except ImportError as exc:
        raise ToolError(
            "pygetwindow is not installed; run install.bat", "missing_dependency"
        ) from exc

    fragment = title.strip().lower()
    matches: list[Any] = []
    try:
        for win in gw.getAllWindows():
            if not win.title or not win.title.strip():
                continue
            if fragment in win.title.lower():
                matches.append(win)
    except Exception as exc:  # noqa: BLE001 - pygetwindow is flaky on Windows
        raise ToolError(f"Could not enumerate windows: {exc}") from exc

    if not matches:
        raise ToolError(f"No open window matches {title!r}.", "window_not_found")

    win = matches[0]
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
    except Exception:  # noqa: BLE001
        try:
            win.minimize()
            win.restore()
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Could not focus {win.title!r}: {exc}") from exc
    return f"Focused {win.title!r}."


def list_running_applications() -> dict[str, Any]:
    """List visible window titles (useful context for the model)."""
    try:
        import pygetwindow as gw
    except ImportError:
        return {"result": "pygetwindow is not installed.", "windows": []}
    titles = sorted({w.title.strip() for w in gw.getAllWindows() if w.title and w.title.strip()})
    return {"result": "\n".join(titles) or "No visible windows.", "windows": titles}


def _deny_open_application(name: str, args: str = "") -> str | None:
    """Guard: block launching interpreters/shells via the app tool.

    Running a shell is intentionally only possible through ``run_safe_command``,
    which is whitelisted and always requires approval.
    """
    forbidden = {"cmd", "command prompt", "powershell", "pwsh", "terminal",
                 "windows terminal", "wscript", "cscript", "mshta", "rundll32",
                 "regsvr32", "bitsadmin", "wmic"}
    if name.strip().lower() in forbidden:
        return (
            f"Launching {name!r} is blocked because it is a shell or script host. "
            "Use run_safe_command for reviewed commands instead."
        )
    return None


open_application.deny_reason = _deny_open_application  # type: ignore[attr-defined]


TOOLS = [
    Tool(
        name="open_application",
        description=(
            "Launch a desktop application by name, e.g. 'chrome', 'notepad', "
            "'vs code', 'spotify', 'obsidian'. Cannot launch shells or script hosts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Application name, e.g. 'chrome'"},
                "args": {"type": "string", "description": "Optional command-line arguments"},
            },
            "required": ["name"],
        },
        handler=open_application,
        level=Level.SAFE,
        timeout=20.0,
        category="apps",
    ),
    Tool(
        name="close_application",
        description="Close a running application by name, e.g. 'notepad'.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Application name"}},
            "required": ["name"],
        },
        handler=close_application,
        level=Level.MODERATE,
        timeout=20.0,
        confirm_template="close the application '{name}' and discard any unsaved changes in it",
        category="apps",
    ),
    Tool(
        name="focus_application",
        description="Bring an already-open window to the front by (part of) its title.",
        parameters={
            "type": "object",
            "properties": {"title": {"type": "string", "description": "Window title fragment"}},
            "required": ["title"],
        },
        handler=focus_application,
        level=Level.SAFE,
        timeout=15.0,
        category="apps",
    ),
    Tool(
        name="list_running_applications",
        description="List titles of currently open windows.",
        parameters={"type": "object", "properties": {}},
        handler=list_running_applications,
        level=Level.SAFE,
        timeout=15.0,
        category="apps",
    ),
]
