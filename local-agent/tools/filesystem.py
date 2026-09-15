"""Filesystem tools: read, write, list, and delete files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from tools.registry import Tool, Level, ToolError


def read_file(path: str) -> str:
    """Read a text file from disk."""
    p = Path(path).expanduser()
    if not p.exists():
        raise ToolError(f"File not found: {path}", "file_not_found")
    if p.is_dir():
        raise ToolError(f"Path is a directory: {path}", "is_a_directory")
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise ToolError(f"Error reading file {path}: {e}", "read_error") from e


def write_file(path: str, content: str) -> str:
    """Write or overwrite a file with content."""
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {path}"
    except Exception as e:
        raise ToolError(f"Error writing file {path}: {e}", "write_error") from e


def list_files(path: str = ".") -> dict[str, Any]:
    """List files and folders in a directory."""
    p = Path(path).expanduser()
    if not p.exists():
        raise ToolError(f"Path not found: {path}", "path_not_found")
    if not p.is_dir():
        raise ToolError(f"Path is not a directory: {path}", "not_a_directory")
    try:
        items = []
        for entry in os.scandir(p):
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        summary = "\n".join(f"[{'DIR' if item['is_dir'] else 'FILE'}] {item['name']}" for item in items)
        return {"result": summary or "(empty directory)", "items": items, "count": len(items)}
    except Exception as e:
        raise ToolError(f"Error listing directory {path}: {e}", "list_error") from e


def delete_file(path: str) -> str:
    """Delete a file permanently. ALWAYS requires confirmation (DANGEROUS)."""
    p = Path(path).expanduser()
    if not p.exists():
        raise ToolError(f"File not found: {path}", "file_not_found")
    if p.is_dir():
        raise ToolError(f"Path is a directory; use a directory removal tool: {path}", "is_a_directory")
    try:
        p.unlink()
        return f"Successfully deleted {path}"
    except Exception as e:
        raise ToolError(f"Error deleting file {path}: {e}", "delete_error") from e


TOOLS = [
    Tool(
        name="read_file",
        description="Read a file's contents from disk.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path to read"}},
            "required": ["path"],
        },
        handler=read_file,
        level=Level.SAFE,
        category="filesystem",
    ),
    Tool(
        name="write_file",
        description="Write text content to a file (creates parents if needed).",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Text content to write"},
            },
            "required": ["path", "content"],
        },
        handler=write_file,
        level=Level.MODERATE,
        confirm_template="write to file '{path}'",
        category="filesystem",
    ),
    Tool(
        name="list_files",
        description="List files and directories within a directory path.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
            },
        },
        handler=list_files,
        level=Level.SAFE,
        category="filesystem",
    ),
    Tool(
        name="delete_file",
        description="Permanently delete a file from disk. Irreversible.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path to delete"}},
            "required": ["path"],
        },
        handler=delete_file,
        level=Level.DANGEROUS,
        confirm_template="permanently delete '{path}'",
        category="filesystem",
    ),
]
