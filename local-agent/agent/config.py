"""Configuration loading for the local agent.

Single source of truth for runtime settings. Precedence (lowest -> highest):

    built-in defaults  <  config/config.json  <  environment variables

Environment variables use the ``LOCALAGENT_`` prefix, e.g. ``LOCALAGENT_MODEL``.
The one exception is ``OLLAMA_HOST`` / ``OLLAMA_MODEL``, which are honoured
directly because Ollama itself uses those names.

No secrets are ever stored here. See ``.env.example``.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "config.json"
CONFIG_EXAMPLE_PATH = CONFIG_DIR / "config.json.example"
LOGS_DIR = PROJECT_ROOT / "logs"
PROMPTS_DIR = PROJECT_ROOT / "prompts"


DEFAULTS: dict[str, Any] = {
    "agent": {
        "name": "Local Agent",
        "personality": "concise, intelligent, practical, calm",
        "tone": "direct",
        "verbosity": "low",
        "confirmation_style": "explicit",
        "max_steps": 8,
        "max_history_messages": 24,
        "max_context_chars": 24000,
        "tool_result_max_chars": 4000,
        "request_timeout": 300,
        "max_retries": 2,
        "temperature": 0.3,
    },
    "ollama": {
        "host": "http://127.0.0.1:11434",
        "model": "qwen3:1.7b",
        "think": False,
        "keep_alive": "5m",
        "num_ctx": 4096,
    },
    "voice": {
        "enabled": False,
        "stt_enabled": True,
        "tts_enabled": True,
        "stt_model": "tiny",
        "stt_device": "cpu",
        "stt_compute_type": "int8",
        "language": "en",
        "ptt_key": "ctrl+alt+space",
        "mic_device": "",
        "vad_silence_seconds": 1.2,
        "max_record_seconds": 20.0,
        "silence_threshold": 0.012,
        "tts_engine": "sapi",
        "tts_voice": "",
        "speed": 1.0,
        "volume": 1.0,
        "max_speak_chars": 1200,
    },
    "memory": {
        "obsidian_vault": "",
        "enabled": True,
        "auto_index": True,
        "max_search_results": 8,
        "snippet_chars": 600,
        "daily_notes_folder": "01 - Daily Notes",
        "inbox_folder": "00 - Inbox",
        "projects_folder": "02 - Projects",
        "personal_folder": "03 - Personal",
        "knowledge_folder": "04 - Knowledge",
        "jobs_folder": "Jobs",
        "resources_folder": "Resources",
    },
    "permissions": {
        "auto_approve_safe": True,
        "auto_approve_moderate": False,
        "auto_approve_dangerous": False,
        "denied_paths": [],
        "allowed_commands": [
            "ipconfig",
            "systeminfo",
            "tasklist",
            "where",
            "Get-Date",
            "Get-Process",
            "Get-ChildItem",
            "Get-Volume",
            "Get-NetIPConfiguration",
        ],
    },
    "visualizer": {
        "enabled": False,
        "bus_dir": "",
        "serve": False,
        "port": 8765,
    },
    "logging": {
        "level": "INFO",
        "max_bytes": 2097152,
        "backup_count": 3,
        "log_transcripts": True,
    },
}


_ENV_MAP: dict[str, tuple[str, str, type]] = {
    # ENV VAR                 -> (section,        key,            caster)
    "LOCALAGENT_NAME": ("agent", "name", str),
    "LOCALAGENT_MODEL": ("ollama", "model", str),
    "OLLAMA_MODEL": ("ollama", "model", str),
    "OLLAMA_HOST": ("ollama", "host", str),
    "LOCALAGENT_HOST": ("ollama", "host", str),
    "LOCALAGENT_NUM_CTX": ("ollama", "num_ctx", int),
    "LOCALAGENT_KEEP_ALIVE": ("ollama", "keep_alive", str),
    "LOCALAGENT_THINK": ("ollama", "think", lambda v: str(v).lower() in ("true", "1", "yes")),
    "LOCALAGENT_MAX_STEPS": ("agent", "max_steps", int),
    "LOCALAGENT_MAX_HISTORY_MESSAGES": ("agent", "max_history_messages", int),
    "LOCALAGENT_MAX_CONTEXT_CHARS": ("agent", "max_context_chars", int),
    "LOCALAGENT_TOOL_RESULT_MAX_CHARS": ("agent", "tool_result_max_chars", int),
    "LOCALAGENT_REQUEST_TIMEOUT": ("agent", "request_timeout", int),
    "LOCALAGENT_MAX_RETRIES": ("agent", "max_retries", int),
    "LOCALAGENT_TEMPERATURE": ("agent", "temperature", float),
    "OBSIDIAN_VAULT_PATH": ("memory", "obsidian_vault", str),
    "LOCALAGENT_VAULT": ("memory", "obsidian_vault", str),
    "LOCALAGENT_STT_MODEL": ("voice", "stt_model", str),
    "LOCALAGENT_LANGUAGE": ("voice", "language", str),
    "LOCALAGENT_TTS_ENGINE": ("voice", "tts_engine", str),
    "LOCALAGENT_TTS_VOICE": ("voice", "tts_voice", str),
    "LOCALAGENT_LOG_LEVEL": ("logging", "level", str),
}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overlay`` into ``base`` and return a new dict."""
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _apply_env(cfg: dict[str, Any]) -> dict[str, Any]:
    for env_name, (section, key, caster) in _ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        try:
            cfg.setdefault(section, {})[key] = caster(raw)
        except (TypeError, ValueError):
            # Ignore unparseable env values rather than crashing at startup.
            continue
    return cfg


# --------------------------------------------------------------------------
# Typed views
# --------------------------------------------------------------------------


@dataclass
class AgentConfig:
    name: str = "Local Agent"
    personality: str = ""
    tone: str = "direct"
    verbosity: str = "low"
    confirmation_style: str = "explicit"
    max_steps: int = 8
    max_history_messages: int = 24
    max_context_chars: int = 24000
    tool_result_max_chars: int = 4000
    request_timeout: int = 300
    max_retries: int = 2
    temperature: float = 0.3


@dataclass
class OllamaConfig:
    host: str = "http://127.0.0.1:11434"
    model: str = "qwen3:1.7b"
    think: bool = False
    keep_alive: str = "5m"
    num_ctx: int = 4096


@dataclass
class VoiceConfig:
    enabled: bool = False
    stt_enabled: bool = True
    tts_enabled: bool = True
    stt_model: str = "tiny"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    language: str = "en"
    ptt_key: str = "ctrl+alt+space"
    mic_device: str = ""
    vad_silence_seconds: float = 1.2
    max_record_seconds: float = 20.0
    silence_threshold: float = 0.012
    tts_engine: str = "sapi"
    tts_voice: str = ""
    speed: float = 1.0
    volume: float = 1.0
    max_speak_chars: int = 1200


@dataclass
class MemoryConfig:
    obsidian_vault: str = ""
    enabled: bool = True
    auto_index: bool = True
    max_search_results: int = 8
    snippet_chars: int = 600
    daily_notes_folder: str = "01 - Daily Notes"
    inbox_folder: str = "00 - Inbox"
    projects_folder: str = "02 - Projects"
    personal_folder: str = "03 - Personal"
    knowledge_folder: str = "04 - Knowledge"
    jobs_folder: str = "Jobs"
    resources_folder: str = "Resources"


@dataclass
class PermissionsConfig:
    auto_approve_safe: bool = True
    auto_approve_moderate: bool = False
    auto_approve_dangerous: bool = False
    denied_paths: list[str] = field(default_factory=list)
    allowed_commands: list[str] = field(default_factory=list)


@dataclass
class VisualizerConfig:
    enabled: bool = False
    bus_dir: str = ""
    serve: bool = False
    port: int = 8765


@dataclass
class LoggingConfig:
    level: str = "INFO"
    max_bytes: int = 2097152
    backup_count: int = 3
    log_transcripts: bool = True


def _build(cls: type, data: dict[str, Any]) -> Any:
    """Instantiate a dataclass from a dict, ignoring unknown keys."""
    known = {f.name for f in fields(cls)}
    clean = {k: v for k, v in data.items() if k in known}
    return cls(**clean)


@dataclass
class Config:
    """Top-level configuration object."""

    agent: AgentConfig = field(default_factory=AgentConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    permissions: PermissionsConfig = field(default_factory=PermissionsConfig)
    visualizer: VisualizerConfig = field(default_factory=VisualizerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    raw: dict[str, Any] = field(default_factory=dict)
    path: str = ""

    # -- construction ------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        """Load config from disk, falling back to defaults when absent."""
        cfg_path = Path(path) if path else CONFIG_PATH
        raw: dict[str, Any] = {}

        if cfg_path.exists():
            try:
                raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ConfigError(
                    f"{cfg_path} is not valid JSON: {exc}\n"
                    "Fix the syntax, or delete the file to regenerate defaults."
                ) from exc
            if not isinstance(raw, dict):
                raise ConfigError(f"{cfg_path} must contain a JSON object.")

        merged = _apply_env(_deep_merge(DEFAULTS, raw))

        return cls(
            agent=_build(AgentConfig, merged["agent"]),
            ollama=_build(OllamaConfig, merged["ollama"]),
            voice=_build(VoiceConfig, merged["voice"]),
            memory=_build(MemoryConfig, merged["memory"]),
            permissions=_build(PermissionsConfig, merged["permissions"]),
            visualizer=_build(VisualizerConfig, merged["visualizer"]),
            logging=_build(LoggingConfig, merged["logging"]),
            raw=merged,
            path=str(cfg_path),
        )

    # -- helpers -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return the plain nested dict (defaults + file + env)."""
        return copy.deepcopy(self.raw)

    def save(self, path: str | Path | None = None) -> Path:
        """Write the effective config to disk, backing up any existing file."""
        target = Path(path) if path else Path(self.path or CONFIG_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = target.with_suffix(target.suffix + ".bak")
            backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        target.write_text(
            json.dumps(self.to_dict(), indent=4) + "\n", encoding="utf-8"
        )
        return target

    @property
    def vault_path(self) -> Path | None:
        """Return the Obsidian vault path if one is configured and exists."""
        if not self.memory.obsidian_vault:
            return None
        p = Path(self.memory.obsidian_vault).expanduser()
        return p if p.exists() else None

    def describe(self) -> str:
        """One-line summary used by diagnostics."""
        vault = self.memory.obsidian_vault or "(not configured)"
        return (
            f"name={self.agent.name!r} model={self.ollama.model!r} "
            f"host={self.ollama.host} vault={vault!r} "
            f"voice={'on' if self.voice.enabled else 'off'}"
        )


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or is invalid."""
