"""Configuration loader for the local assistant.

Priority (highest to lowest):
  1. Environment variables  (OLLAMA_HOST, OLLAMA_MODEL, VAULT_PATH, ...)
  2. .env file              (project root, optional)
  3. config.json            (project root, optional)
  4. Built-in defaults

No third-party libraries required.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "ollama": {
        "host": "http://127.0.0.1:11434",
        "model": "qwen3:1.7b",
        "timeout": 120,
    },
    "obsidian": {
        "vault": "",
        "max_results": 8,
    },
    "voice": {
        "enabled": True,
        "language": "en",
        "stt_model": "tiny",
        "silence_seconds": 1.0,
        "max_record_seconds": 12,
        "silence_threshold": 0.012,
    },
    "tts": {
        "enabled": True,
        "voice": "",
        "rate": 165,
    },
}

# Root of the project (directory containing main.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a minimal .env file: KEY=VALUE, skip comments and blank lines."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return result
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def _load_json_config(path: Path) -> dict:
    """Load config.json, return {} on any failure."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load(project_root: Path | None = None) -> dict:
    """Return the merged configuration dictionary."""
    root = Path(project_root) if project_root else _PROJECT_ROOT

    # Start from defaults (deep copy)
    config = {section: dict(values) for section, values in DEFAULTS.items()}

    # Layer 3: config.json
    json_cfg = _load_json_config(root / "config.json")
    for section, values in config.items():
        if isinstance(json_cfg.get(section), dict):
            values.update(json_cfg[section])

    # Layer 2: .env file
    env_vars = _load_env_file(root / ".env")
    # Also merge environment variables from the OS into our env_vars dict
    # (OS env takes priority over .env file)
    env_vars.update(os.environ)

    # Apply known env var overrides
    _apply_env(config, env_vars)

    return config


def _apply_env(config: dict, env: dict[str, str]) -> None:
    """Apply recognized environment variable overrides into config."""

    def get(key: str) -> str | None:
        return env.get(key) or None

    def get_bool(key: str) -> bool | None:
        v = env.get(key)
        if v is None:
            return None
        return v.strip().lower() not in ("0", "false", "no", "off", "")

    if v := get("OLLAMA_HOST"):
        config["ollama"]["host"] = v
    if v := get("OLLAMA_MODEL"):
        config["ollama"]["model"] = v
    if v := get("OLLAMA_TIMEOUT"):
        try:
            config["ollama"]["timeout"] = float(v)
        except ValueError:
            pass
    if v := get("VAULT_PATH"):
        config["obsidian"]["vault"] = v
    if v := get("OBSIDIAN_MAX_RESULTS"):
        try:
            config["obsidian"]["max_results"] = int(v)
        except ValueError:
            pass
    if (v := get_bool("VOICE_ENABLED")) is not None:
        config["voice"]["enabled"] = v
    if (v := get_bool("TTS_ENABLED")) is not None:
        config["tts"]["enabled"] = v
