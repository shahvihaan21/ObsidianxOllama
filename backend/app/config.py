"""Configuration for the Obsidian control system.

Priority (highest first):

    1. environment variables
    2. backend/.env            (optional)
    3. backend/config.json     (optional)
    4. the defaults below

There are only four sections, because the application does only four things:
control the vault, use a local LLM for text work, listen to a microphone, and
research the web for a note. Anything else is not configurable because it does
not exist.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = BACKEND_ROOT / "config.json"
ENV_FILE = BACKEND_ROOT / ".env"

DEFAULTS: dict = {
    "server": {
        "host": "127.0.0.1",
        "port": 8765,
    },
    "obsidian": {
        # Absolute path to the vault folder. Empty means "not configured".
        "vault": "",
        # How many search results / notes to show at most.
        "max_results": 8,
        # Characters of context kept for a search hit.
        "snippet_chars": 240,
        # Vault-relative folder used when trashing without the Obsidian plugin.
        "trash_folder": ".trash",
    },
    "llm": {
        "enabled": True,
        "host": "http://127.0.0.1:11434",
        "model": "qwen3:1.7b",
        "timeout": 120,
        "temperature": 0.2,
    },
    "voice": {
        "enabled": True,
        "language": "en",
        "stt_model": "tiny",
        "silence_seconds": 1.0,
        "max_record_seconds": 12,
        "silence_threshold": 0.012,
        "wait_for_speech_seconds": 5.0,
    },
    "research": {
        "enabled": True,
        "max_queries": 3,
        "max_sources": 5,
        "timeout": 15,
        # Any endpoint returning DuckDuckGo-style HTML search results works.
        "search_url": "https://html.duckduckgo.com/html/?q={query}",
        "user_agent": "Mozilla/5.0 (compatible; ObsidianControl/1.0)",
    },
}

# Environment variable -> (section, key, converter)
_ENV_MAP: dict[str, tuple[str, str, str]] = {
    "VAULT_PATH": ("obsidian", "vault", "str"),
    "OBSIDIAN_VAULT": ("obsidian", "vault", "str"),
    "OBSIDIAN_MAX_RESULTS": ("obsidian", "max_results", "int"),
    "LLM_ENABLED": ("llm", "enabled", "bool"),
    "LLM_HOST": ("llm", "host", "str"),
    "LLM_MODEL": ("llm", "model", "str"),
    "LLM_TIMEOUT": ("llm", "timeout", "float"),
    "OLLAMA_HOST": ("llm", "host", "str"),
    "OLLAMA_MODEL": ("llm", "model", "str"),
    "VOICE_ENABLED": ("voice", "enabled", "bool"),
    "VOICE_LANGUAGE": ("voice", "language", "str"),
    "VOICE_STT_MODEL": ("voice", "stt_model", "str"),
    "RESEARCH_ENABLED": ("research", "enabled", "bool"),
    "RESEARCH_MAX_SOURCES": ("research", "max_sources", "int"),
    "SERVER_HOST": ("server", "host", "str"),
    "SERVER_PORT": ("server", "port", "int"),
}

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _convert(value: str, kind: str):
    """Convert an environment variable, or return None when it is unusable."""
    text = str(value).strip()
    try:
        if kind == "bool":
            lowered = text.lower()
            if lowered in _TRUE:
                return True
            if lowered in _FALSE:
                return False
            return None
        if kind == "int":
            return int(text)
        if kind == "float":
            return float(text)
    except ValueError:
        return None
    return text


def _read_json(path: Path) -> dict:
    try:
        # utf-8-sig tolerates a byte-order mark written by Windows editors.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a minimal ``KEY=VALUE`` .env file."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def load(project_root: Path | None = None) -> dict:
    """Return the merged configuration dictionary."""
    root = Path(project_root) if project_root else BACKEND_ROOT
    config = {section: dict(values) for section, values in DEFAULTS.items()}

    stored = _read_json(root / "config.json")
    for section, values in config.items():
        if isinstance(stored.get(section), dict):
            values.update(stored[section])

    environment = _read_env_file(root / ".env")
    environment.update(os.environ)
    for name, (section, key, kind) in _ENV_MAP.items():
        raw = environment.get(name)
        if raw is None:
            continue
        value = _convert(raw, kind)
        if value is not None:
            config[section][key] = value

    return config