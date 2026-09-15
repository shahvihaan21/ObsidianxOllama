"""Filesystem tools."""

from tools.registry import Tool, Level
from typing import Any

def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"

TOOLS = [
    Tool(
        name="read_file",
        description="Read a file's contents.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        },
        handler=read_file,
        level=Level.SAFE
    )
]
