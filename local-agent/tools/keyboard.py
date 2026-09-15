"""Keyboard control: typing, single keys, and hotkeys.

All handlers go through ``pyautogui``. A short settle delay is applied before
typing so the target window has time to take focus.
"""

from __future__ import annotations

import logging
import time

from tools.registry import Level, Tool, ToolError

log = logging.getLogger(__name__)

# pyautogui key names we accept. Anything outside this set is rejected, so a
# model cannot ask us to press something nonsensical.
VALID_KEYS = {
    "enter", "return", "tab", "space", "backspace", "delete", "esc", "escape",
    "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
    "insert", "capslock", "numlock", "printscreen", "pause",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
}

MODIFIERS = {"ctrl", "alt", "shift", "win", "cmd", "meta"}

# Combos that touch the OS rather than the focused app.
FORBIDDEN_HOTKEYS = {
    ("win", "r"),      # Run dialog
    ("win", "x"),      # admin menu
    ("ctrl", "alt", "delete"),
    ("win", "l"),      # lock screen
    ("alt", "f4"),     # close/force-quit active window (use close_application)
    ("win", "s"),      # search (harmless but noisy)
}


def _pyautogui():
    try:
        import pyautogui
    except ImportError as exc:
        raise ToolError(
            "pyautogui is not installed. Run install.bat to install the "
            "computer-control dependencies.",
            "missing_dependency",
        ) from exc
    pyautogui.FAILSAFE = True  # slam the mouse into a corner to abort
    pyautogui.PAUSE = 0.02
    return pyautogui


def type_text(text: str, interval: float = 0.01, press_enter: bool = False) -> str:
    """Type text into whatever window has focus."""
    if not text:
        raise ToolError("No text to type.", "bad_arguments")
    gui = _pyautogui()
    time.sleep(0.25)  # let the focus change settle before we start typing
    try:
        gui.typewrite(text, interval=max(0.0, min(interval, 0.2)))
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"Typing failed: {exc}", "input_failed") from exc
    if press_enter:
        gui.press("enter")
    preview = text if len(text) <= 60 else text[:57] + "..."
    return f"Typed: {preview}"


def press_key(key: str, presses: int = 1) -> str:
    """Press a single non-printing key, e.g. 'enter' or 'tab'."""
    gui = _pyautogui()
    normalised = key.strip().lower()
    if normalised not in VALID_KEYS:
        raise ToolError(
            f"{key!r} is not an allowed key. Allowed: "
            f"{', '.join(sorted(VALID_KEYS))}",
            "bad_arguments",
        )
    count = max(1, min(int(presses), 50))
    gui.press(normalised, presses=count)
    return f"Pressed {normalised}" + (f" x{count}" if count > 1 else "")


def hotkey(keys: str) -> str:
    """Press a key combination, e.g. 'ctrl+s' or 'ctrl+shift+t'."""
    gui = _pyautogui()
    parts = [p.strip().lower() for p in keys.replace("+", " ").split() if p.strip()]
    if not parts:
        raise ToolError("No keys provided.", "bad_arguments")
    if len(parts) == 1:
        return press_key(parts[0])

    # A letter typed with a modifier is valid; so are the known modifiers/keys.
    for part in parts:
        if part in MODIFIERS or part in VALID_KEYS:
            continue
        if len(part) == 1 and part.isalnum():
            continue
        raise ToolError(
            f"{part!r} is not a valid key in combination {keys!r}.", "bad_arguments"
        )

    combo = tuple(sorted(parts))
    if combo in FORBIDDEN_HOTKEYS:
        raise ToolError(
            f"The combination {keys!r} is blocked because it affects the "
            "operating system or can close windows unexpectedly.",
            "unsafe_hotkey",
        )

    try:
        gui.hotkey(*parts)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"Hotkey failed: {exc}", "input_failed") from exc
    return f"Pressed {'+'.join(parts)}"


def get_active_window() -> dict[str, str]:
    """Report the title of the focused window."""
    try:
        import pygetwindow as gw
    except ImportError:
        return {"result": "pygetwindow is not installed."}
    try:
        win = gw.getActiveWindow()
    except Exception as exc:  # noqa: BLE001
        return {"result": f"Could not determine the active window: {exc}"}
    title = getattr(win, "title", "") or "(no title)"
    return {"result": f"Active window: {title}", "title": title}


TOOLS = [
    Tool(
        name="type_text",
        description=(
            "Type text into the currently focused window. Focus a window first "
            "with focus_application or open_application."
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
                "press_enter": {
                    "type": "boolean",
                    "description": "Press Enter after typing",
                    "default": False,
                },
            },
            "required": ["text"],
        },
        handler=lambda text, press_enter=False: type_text(text, press_enter=press_enter),
        level=Level.SAFE,
        timeout=30.0,
        category="input",
    ),
    Tool(
        name="press_key",
        description="Press a single key such as enter, tab, esc, backspace, up, down, f5.",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name, e.g. 'enter'"},
                "presses": {"type": "integer", "description": "How many times", "default": 1},
            },
            "required": ["key"],
        },
        handler=press_key,
        level=Level.SAFE,
        timeout=15.0,
        category="input",
    ),
    Tool(
        name="hotkey",
        description=(
            "Press a key combination such as 'ctrl+s', 'ctrl+c', 'ctrl+shift+t'. "
            "OS-level combinations like 'win+r' and 'alt+f4' are blocked."
        ),
        parameters={
            "type": "object",
            "properties": {"keys": {"type": "string", "description": "Combination, e.g. 'ctrl+s'"}},
            "required": ["keys"],
        },
        handler=hotkey,
        level=Level.SAFE,
        timeout=15.0,
        category="input",
    ),
    Tool(
        name="get_active_window",
        description="Report which window currently has focus.",
        parameters={"type": "object", "properties": {}},
        handler=get_active_window,
        level=Level.SAFE,
        timeout=10.0,
        category="input",
    ),
]