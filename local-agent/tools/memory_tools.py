"""Obsidian memory integration."""

import os
import json
from pathlib import Path
from tools.registry import Tool, Level, ToolError
from typing import Any

# Read config from environment or use a default
# We can just rely on the vault_path passed in, or read from LOCALAGENT_VAULT
def _get_vault() -> Path:
    vault = os.environ.get("LOCALAGENT_VAULT") or os.environ.get("OBSIDIAN_VAULT_PATH")
    if not vault:
        try:
            from agent.config import Config
            vault = Config.load().memory.obsidian_vault
        except Exception:
            vault = ""
    if not vault:
        raise ToolError(
            "Obsidian vault path not configured. Set LOCALAGENT_VAULT or configure memory.obsidian_vault in config/config.json.",
            "config_error",
        )
    p = Path(vault).expanduser()
    if not p.exists():
        raise ToolError(f"Obsidian vault path '{p}' does not exist.", "vault_not_found")
    return p


def search_memory(query: str, max_results: int = 8) -> str:
    """Search Obsidian vault for the given query."""
    vault = _get_vault()
    results = []
    q = query.strip().lower()
    if not q:
        raise ToolError("Query cannot be empty.", "bad_arguments")
    # walk the vault looking for markdown files matching query
    for root, dirs, files in os.walk(vault):
        for file in files:
            if file.endswith(".md"):
                path = Path(root) / file
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    if q in content.lower() or q in file.lower():
                        results.append(str(path.relative_to(vault)))
                        if len(results) >= max_results:
                            break
                except Exception:
                    pass
        if len(results) >= max_results:
            break
    if not results:
        return "No results found in Obsidian vault."
    return "Found in vault:\n" + "\n".join(f"- {r}" for r in results)


def read_obsidian_note(name: str) -> str:
    """Read a specific note from the vault."""
    vault = _get_vault()
    clean_name = name.strip()
    if not clean_name.endswith(".md"):
        clean_name += ".md"
    note_path = vault / clean_name
    if not note_path.exists():
        raise ToolError(f"Note '{name}' not found in vault.", "note_not_found")
    try:
        return note_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise ToolError(f"Failed to read note '{name}': {e}", "read_error") from e


def create_obsidian_note(name: str, content: str) -> str:
    """Create a new note in the vault."""
    vault = _get_vault()
    clean_name = name.strip()
    if not clean_name.endswith(".md"):
        clean_name += ".md"
    note_path = vault / clean_name
    if note_path.exists():
        raise ToolError(f"Note '{name}' already exists in vault.", "note_exists")
    try:
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content, encoding="utf-8")
        return f"Note '{name}' created successfully."
    except Exception as e:
        raise ToolError(f"Failed to create note '{name}': {e}", "create_error") from e


def append_obsidian_note(name: str, content: str) -> str:
    """Append to an existing note."""
    vault = _get_vault()
    clean_name = name.strip()
    if not clean_name.endswith(".md"):
        clean_name += ".md"
    note_path = vault / clean_name
    if not note_path.exists():
        raise ToolError(f"Note '{name}' does not exist in vault.", "note_not_found")
    try:
        with open(note_path, "a", encoding="utf-8") as f:
            f.write("\n" + content)
        return f"Appended to note '{name}' successfully."
    except Exception as e:
        raise ToolError(f"Failed to append to note '{name}': {e}", "append_error") from e


TOOLS = [
    Tool(
        name="search_memory",
        description="Search Obsidian memory/notes for a given query.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Maximum number of notes to return", "default": 8},
            },
            "required": ["query"],
        },
        handler=search_memory,
        level=Level.SAFE,
        category="obsidian",
    ),
    Tool(
        name="read_obsidian_note",
        description="Read an Obsidian note by filename (relative to vault root).",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Note filename or path"}},
            "required": ["name"],
        },
        handler=read_obsidian_note,
        level=Level.SAFE,
        category="obsidian",
    ),
    Tool(
        name="create_obsidian_note",
        description="Create a new Obsidian note.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Note filename or relative path"},
                "content": {"type": "string", "description": "Markdown content"},
            },
            "required": ["name", "content"],
        },
        handler=create_obsidian_note,
        level=Level.MODERATE,
        confirm_template="create note '{name}' in Obsidian vault",
        category="obsidian",
    ),
    Tool(
        name="append_obsidian_note",
        description="Append text to an existing Obsidian note.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Note filename or relative path"},
                "content": {"type": "string", "description": "Text to append"},
            },
            "required": ["name", "content"],
        },
        handler=append_obsidian_note,
        level=Level.MODERATE,
        confirm_template="append to note '{name}' in Obsidian vault",
        category="obsidian",
    ),
]
