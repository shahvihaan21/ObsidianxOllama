"""Obsidian memory integration."""

import os
import json
from pathlib import Path
from tools.registry import Tool, Level, ToolError
from typing import Any

# Read config from environment or use a default
# We can just rely on the vault_path passed in, or read from LOCALAGENT_VAULT
def _get_vault() -> Path:
    vault = os.environ.get("LOCALAGENT_VAULT")
    if not vault:
        raise ToolError("Obsidian vault path not configured.", "config_error")
    p = Path(vault).expanduser()
    if not p.exists():
        raise ToolError(f"Vault path {p} does not exist.", "config_error")
    return p

def search_memory(query: str) -> str:
    """Search Obsidian vault for the given query."""
    vault = _get_vault()
    results = []
    # simple brute force search for demo
    for root, dirs, files in os.walk(vault):
        for file in files:
            if file.endswith(".md"):
                path = Path(root) / file
                try:
                    content = path.read_text(encoding="utf-8")
                    if query.lower() in content.lower():
                        results.append(str(path.relative_to(vault)))
                except Exception:
                    pass
    if not results:
        return "No results found."
    return "Found in:\n" + "\n".join(results)

def read_obsidian_note(name: str) -> str:
    """Read a specific note from the vault."""
    vault = _get_vault()
    if not name.endswith(".md"):
        name += ".md"
    note_path = vault / name
    if not note_path.exists():
        return f"Note {name} not found."
    return note_path.read_text(encoding="utf-8")

def create_obsidian_note(name: str, content: str) -> str:
    """Create a new note in the vault."""
    vault = _get_vault()
    if not name.endswith(".md"):
        name += ".md"
    note_path = vault / name
    if note_path.exists():
        return f"Note {name} already exists."
    note_path.write_text(content, encoding="utf-8")
    return f"Note {name} created."

def append_obsidian_note(name: str, content: str) -> str:
    """Append to an existing note."""
    vault = _get_vault()
    if not name.endswith(".md"):
        name += ".md"
    note_path = vault / name
    if not note_path.exists():
        return f"Note {name} does not exist."
    with open(note_path, "a", encoding="utf-8") as f:
        f.write("\n" + content)
    return f"Appended to note {name}."

TOOLS = [
    Tool(
        name="search_memory",
        description="Search Obsidian memory for a given query.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        handler=search_memory,
        level=Level.SAFE
    ),
    Tool(
        name="read_obsidian_note",
        description="Read an Obsidian note.",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=read_obsidian_note,
        level=Level.SAFE
    ),
    Tool(
        name="create_obsidian_note",
        description="Create an Obsidian note.",
        parameters={"type": "object", "properties": {"name": {"type": "string"}, "content": {"type": "string"}}, "required": ["name", "content"]},
        handler=create_obsidian_note,
        level=Level.MODERATE
    ),
    Tool(
        name="append_obsidian_note",
        description="Append to an Obsidian note.",
        parameters={"type": "object", "properties": {"name": {"type": "string"}, "content": {"type": "string"}}, "required": ["name", "content"]},
        handler=append_obsidian_note,
        level=Level.MODERATE
    )
]
