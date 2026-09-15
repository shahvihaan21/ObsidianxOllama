"""Mouse control: move, click, double-click, scroll.

Screen coordinates are validated against the actual desktop size so the model
cannot drive the cursor off-screen. ``pyautogui.FAILSAFE`` stays enabled: moving
the pointer into a screen corner aborts a runaway action.
"""

from __future__ import annotations

import logging
import time

from tools.registry import Level, Tool, ToolError

log = logging.getLogger(__name__)

VALID_BUTTONS = {"left", "right", "middle"}


def _pyautogui():
    try:
        import pyautogui
    except ImportError as exc:
        raise ToolError(
            "pyautogui is not installed. Run install.bat.", "missing_dependency"
        ) from exc
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02
    return pyautogui


def _screen_size() -> tuple[int, int]:
    gui = _pyautogui()
    size = gui.size()
    return int(size[0]), int(size[1])


def _validate_point(x: int, y: int) -> tuple[int, int]:
    width, height = _screen_size()
    px, py = int(x), int(y)
    if not (0 <= px < width and 0 <= py < height):
        raise ToolError(
            f"Point ({px}, {py}) is outside the screen ({width}x{height}).",
            "out_of_bounds",
        )
    return px, py


def mouse_position() -> dict[str, int]:
    """Report the current cursor position."""
    gui = _pyautogui()
    pos = gui.position()
    return {"result": f"Cursor is at ({pos.x}, {pos.y}).", "x": int(pos.x), "y": int(pos.y)}


def mouse_move(x: int, y: int, duration: float = 0.2) -> str:
    """Move the cursor to a point."""
    gui = _pyautogui()
    px, py = _validate_point(x, y)
    gui.moveTo(px, py, duration=max(0.0, min(float(duration), 2.0)))
    return f"Moved the cursor to ({px}, {py})."


def mouse_click(
    x: int | None = None, y: int | None = None, button: str = "left"
) -> str:
    """Click, optionally moving to a point first."""
    gui = _pyautogui()
    btn = (button or "left").strip().lower()
    if btn not in VALID_BUTTONS:
        raise ToolError(
            f"Unknown mouse button {button!r}. Use left, right, or middle.",
            "bad_arguments",
        )
    where = "the current position"
    if x is not None and y is not None:
        px, py = _validate_point(x, y)
        gui.moveTo(px, py, duration=0.15)
        where = f"({px}, {py})"
    time.sleep(0.1)
    gui.click(button=btn)
    return f"Clicked ({btn}) at {where}."


def double_click(
    x: int | None = None, y: int | None = None, button: str = "left"
) -> str:
    """Double-click, optionally moving to a point first."""
    gui = _pyautogui()
    btn = (button or "left").strip().lower()
    if btn not in VALID_BUTTONS:
        raise ToolError(f"Unknown mouse button {button!r}.", "bad_arguments")
    where = "the current position"
    if x is not None and y is not None:
        px, py = _validate_point(x, y)
        gui.moveTo(px, py, duration=0.15)
        where = f"({px}, {py})"
    gui.doubleClick(button=btn)
    return f"Double-clicked ({btn}) at {where}."


def scroll(clicks: int, x: int | None = None, y: int | None = None) -> str:
    """Scroll vertically. Positive scrolls up, negative scrolls down."""
    gui = _pyautogui()
    amount = int(clicks)
    if amount == 0:
        raise ToolError("Scroll amount cannot be zero.", "bad_arguments")
    amount = max(-50, min(amount, 50))
    if x is not None and y is not None:
        px, py = _validate_point(x, y)
        gui.moveTo(px, py, duration=0.15)
    gui.scroll(amount)
    direction = "up" if amount > 0 else "down"
    return f"Scrolled {direction} by {abs(amount)}."


TOOLS = [
    Tool(
        name="mouse_position",
        description="Report the current mouse cursor coordinates.",
        parameters={"type": "object", "properties": {}},
        handler=mouse_position,
        level=Level.SAFE,
        timeout=10.0,
        category="input",
    ),
    Tool(
        name="mouse_move",
        description="Move the mouse cursor to screen coordinates.",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X pixel"},
                "y": {"type": "integer", "description": "Y pixel"},
            },
            "required": ["x", "y"],
        },
        handler=mouse_move,
        level=Level.SAFE,
        timeout=15.0,
        category="input",
    ),
    Tool(
        name="mouse_click",
        description="Click the mouse, optionally at given coordinates.",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X pixel (optional)"},
                "y": {"type": "integer", "description": "Y pixel (optional)"},
                "button": {"type": "string", "description": "left, right, or middle", "default": "left"},
            },
        },
        handler=mouse_click,
        level=Level.SAFE,
        timeout=15.0,
        category="input",
    ),
    Tool(
        name="double_click",
        description="Double-click, optionally at given coordinates.",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X pixel (optional)"},
                "y": {"type": "integer", "description": "Y pixel (optional)"},
                "button": {"type": "string", "description": "left, right, or middle", "default": "left"},
            },
        },
        handler=double_click,
        level=Level.SAFE,
        timeout=15.0,
        category="input",
    ),
    Tool(
        name="scroll",
        description="Scroll the mouse wheel. Positive is up, negative is down.",
        parameters={
            "type": "object",
            "properties": {
                "clicks": {"type": "integer", "description": "Wheel clicks; negative scrolls down"},
                "x": {"type": "integer", "description": "X pixel (optional)"},
                "y": {"type": "integer", "description": "Y pixel (optional)"},
            },
            "required": ["clicks"],
        },
        handler=scroll,
        level=Level.SAFE,
        timeout=15.0,
        category="input",
    ),
]