"""Obsidian vault access: search, read, create, append.

The configured vault is the security boundary. Every requested path is resolved
on the real filesystem and checked against the vault before anything is read or
written, so ``../../test.txt`` and absolute paths outside the vault are rejected.

This is deliberately simple vault search: filename + markdown text. No index,
no embeddings, no vector database, no "semantic memory".
"""

from __future__ import annotations

import os
import re
from pathlib import Path

NOT_CONFIGURED = "Obsidian vault is not configured."
NOTE_EXISTS = "That note already exists."
NOTE_NOT_FOUND = "Note not found."
OUTSIDE_VAULT = "That path is outside your Obsidian vault."

_INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


class ObsidianError(RuntimeError):
    """A clean, expected vault failure (missing note, bad path, no vault)."""


class Obsidian:
    """Minimal Obsidian vault reader/writer."""

    def __init__(
        self, vault: str = "", max_results: int = 8, snippet_chars: int = 240
    ) -> None:
        self.vault = self._prepare_vault(vault)
        self.max_results = max(1, int(max_results))
        self.snippet_chars = max(40, int(snippet_chars))

    # -- configuration --------------------------------------------------

    @staticmethod
    def _prepare_vault(vault: str) -> Path | None:
        raw = str(vault or "").strip().strip('"')
        if not raw:
            return None
        path = Path(os.path.expanduser(os.path.expandvars(raw)))
        if not path.is_dir():
            return None
        return Path(os.path.realpath(path))

    @property
    def configured(self) -> bool:
        return self.vault is not None

    def describe(self) -> str:
        return str(self.vault) if self.vault else "not configured"

    def _require_vault(self) -> Path:
        if self.vault is None:
            raise ObsidianError(NOT_CONFIGURED)
        return self.vault

    # -- paths ----------------------------------------------------------

    @staticmethod
    def _clean(name: str) -> str:
        return str(name or "").strip().strip('"').strip("'").strip()

    def _sanitize(self, name: str) -> str:
        """Return a vault-relative path, or raise if it tries to escape.

        Traversal (``..``) and absolute/drive-qualified paths are rejected
        outright rather than quietly normalised back into the vault.
        """
        raw = self._clean(name)
        if not raw:
            raise ObsidianError("No note name was given.")
        candidate = Path(raw)
        if candidate.is_absolute() or candidate.drive:
            raise ObsidianError(OUTSIDE_VAULT)

        parts: list[str] = []
        for part in re.split(r"[\\/]+", raw):
            if part == "..":
                raise ObsidianError(OUTSIDE_VAULT)
            if part == ".":
                continue
            part = _INVALID_CHARS.sub("", part).strip().rstrip(". ")
            if part:
                parts.append(part)
        if not parts:
            raise ObsidianError("No note name was given.")
        return "/".join(parts)

    @staticmethod
    def _force_markdown(name: str) -> str:
        """Notes are always markdown: 'Ideas', 'Ideas.txt' -> 'Ideas.md'."""
        if name.lower().endswith(".md"):
            return name
        head, _, tail = name.rpartition("/")
        if "." in tail:
            tail = tail.rsplit(".", 1)[0]
        tail += ".md"
        return f"{head}/{tail}" if head else tail

    def resolve(self, name: str) -> Path:
        """Resolve *name* inside the vault, or raise :class:`ObsidianError`."""
        vault = self._require_vault()
        relative = self._force_markdown(self._sanitize(name))
        target = Path(os.path.realpath(os.path.join(vault, relative)))
        # Defence in depth: the resolved path must really live inside the vault.
        if target != vault and vault not in target.parents:
            raise ObsidianError(OUTSIDE_VAULT)
        return target

    def note_path_for(self, note: str) -> str:
        """Vault-relative path used in confirmation prompts (note need not exist)."""
        vault = self._require_vault()
        return self.resolve(note).relative_to(vault).as_posix()

    # -- search ---------------------------------------------------------

    def search(self, query: str, max_results: int | None = None) -> list[dict[str, str]]:
        """Match *query* against note filenames and markdown contents.

        Files are read one at a time; nothing is indexed or kept in memory.
        """
        vault = self._require_vault()
        needle = " ".join(str(query or "").split()).lower()
        if not needle:
            raise ObsidianError("No search query was given.")
        limit = self.max_results if max_results is None else max(1, int(max_results))

        hits: list[dict[str, str]] = []
        for root, dirs, files in os.walk(vault):
            dirs[:] = sorted(name for name in dirs if not name.startswith("."))
            for filename in sorted(files):
                if not filename.lower().endswith(".md"):
                    continue
                path = Path(root) / filename
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if needle not in filename.lower() and needle not in text.lower():
                    continue
                hits.append(
                    {
                        "note": path.relative_to(vault).as_posix(),
                        "snippet": self._snippet(text, needle),
                    }
                )

        hits.sort(
            key=lambda hit: (0 if needle in hit["note"].lower() else 1, hit["note"].lower())
        )
        return hits[:limit]

    def _snippet(self, text: str, needle: str) -> str:
        flat = " ".join(text.split())
        index = flat.lower().find(needle)
        if index < 0:
            return flat[: self.snippet_chars]
        start = max(0, index - self.snippet_chars // 3)
        return flat[start : start + self.snippet_chars].strip()

    # -- read -----------------------------------------------------------

    def read(self, note: str) -> str:
        path = self.resolve(note)
        if not path.is_file():
            raise ObsidianError(NOTE_NOT_FOUND)
        return path.read_text(encoding="utf-8", errors="replace")

    def exists(self, note: str) -> bool:
        return self.resolve(note).is_file()

    # -- write ----------------------------------------------------------

    def create(self, note: str, content: str = "") -> str:
        """Create a new note. Never overwrites, never leaves the vault."""
        vault = self._require_vault()
        path = self.resolve(note)
        if path.exists():
            raise ObsidianError(NOTE_EXISTS)
        parent = path.parent
        if parent != vault and not parent.is_dir():
            parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content or ""), encoding="utf-8")
        relative = path.relative_to(vault).as_posix()
        return f'Created "{relative}" in your Obsidian vault.'

    def append(self, note: str, content: str) -> str:
        """Append to an existing note. Never creates one."""
        vault = self._require_vault()
        path = self.resolve(note)
        if not path.is_file():
            raise ObsidianError(NOTE_NOT_FOUND)
        body = str(content or "").strip()
        if not body:
            raise ObsidianError("Nothing to append.")
        separator = "\n" if path.stat().st_size else ""
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{separator}{body}\n")
        relative = path.relative_to(vault).as_posix()
        return f'Appended to "{relative}".'


def format_results(results: list[dict[str, str]]) -> str:
    """Render search hits for the console."""
    if not results:
        return "No notes found in your Obsidian vault."
    lines = [f"Found {len(results)} note(s):"]
    for hit in results:
        lines.append(f"- {hit['note']}")
        snippet = hit.get("snippet") or ""
        if snippet:
            lines.append(f"  {snippet}")
    return "\n".join(lines)
