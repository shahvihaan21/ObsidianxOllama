"""FastAPI backend for the local assistant.

Provides a lightweight HTTP API:

    GET  /api/health      - backend status
    POST /api/chat        - send a message
    POST /api/voice       - trigger voice interaction

The backend owns Ollama, STT, TTS, command routing, tool execution,
Obsidian access, app launching, Google search and confirmation.

The frontend is only the interface.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .core import Assistant, default_confirm
from .obsidian import Obsidian
from .ollama import Ollama
from .tools import Tools
from .voice import Voice

log = logging.getLogger("app")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR.parent / "config.json"

DEFAULT_CONFIG: dict = {
    "ollama": {
        "host": "http://127.0.0.1:11434",
        "model": "qwen3:1.7b",
        "timeout": 120,
    },
    "obsidian": {"vault": "", "max_results": 8},
    "voice": {
        "enabled": True,
        "language": "en",
        "stt_model": "tiny",
        "silence_seconds": 1.0,
        "max_record_seconds": 12,
        "silence_threshold": 0.012,
    },
    "tts": {"enabled": True, "voice": "", "rate": 165},
}


def load_config(path: Path | str | None = None) -> dict:
    config = {section: dict(values) for section, values in DEFAULT_CONFIG.items()}
    file_path = Path(path) if path else CONFIG_PATH
    if not file_path.is_file():
        log.info("No config file at %s; using built-in defaults.", file_path)
        return config
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Config at %s could not be read (%s); using defaults.", file_path, exc)
        return config
    for section, values in config.items():
        if isinstance(raw.get(section), dict):
            values.update(raw[section])
    return config


_config = load_config()

_ollama = Ollama(
    host=_config["ollama"]["host"],
    model=_config["ollama"]["model"],
    timeout=_config["ollama"]["timeout"],
)
_obsidian = Obsidian(
    vault=_config["obsidian"]["vault"],
    max_results=_config["obsidian"]["max_results"],
)
_voice = Voice(voice_config=_config["voice"], tts_config=_config["tts"])
_assistant = Assistant(
    ollama=_ollama,
    tools=Tools(obsidian=_obsidian),
    confirm=default_confirm,
    voice=_voice,
)


def _status_dict() -> dict[str, Any]:
    ollama_ok = bool(_ollama.is_available())
    obsidian_ok = bool(_obsidian.configured)
    voice_ok = bool(_voice.available)
    return {
        "status": "ok" if (ollama_ok and voice_ok) else "degraded",
        "ollama": ollama_ok,
        "model": str(_ollama.model),
        "voice": voice_ok,
        "obsidian": obsidian_ok,
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Local Assistant API", version="1.0.0")

# CORS: only the Vite frontend during local development.
_FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return _status_dict()


@app.post("/api/chat")
def chat(payload: dict[str, Any]) -> dict[str, Any]:
    message = (payload or {}).get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        response = _assistant.handle(message)
    except Exception as exc:
        log.exception("Unhandled error processing message: %s", exc)
        raise HTTPException(status_code=500, detail="Internal assistant error.")

    if _assistant.should_exit:
        _assistant.should_exit = False

    return {"success": True, "response": response or ""}


@app.post("/api/voice")
def voice_interaction(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not _voice.available:
        raise HTTPException(status_code=503, detail=f"Voice unavailable: {_voice.reason}")

    try:
        transcript = _voice.listen().strip()
    except Exception as exc:
        log.exception("Voice recording failed: %s", exc)
        raise HTTPException(status_code=500, detail="Voice recording failed.")

    if not transcript:
        return {
            "success": False,
            "error": "Nothing was said, or speech was not understood.",
            "transcript": "",
            "response": "",
        }

    try:
        response = _assistant.handle(transcript)
    except Exception as exc:
        log.exception("Voice processing failed: %s", exc)
        response = f"Something went wrong: {exc}"

    if response and _voice.tts_enabled and _assistant.voice_enabled is not False:
        try:
            _voice.speak(response)
        except Exception:
            log.warning("TTS failed during voice interaction.")

    if _assistant.should_exit:
        _assistant.should_exit = False

    return {
        "success": True,
        "transcript": transcript,
        "response": response or "",
    }


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "ollama": _ollama.is_available(),
        "model": _ollama.model,
        "ollama_problem": _ollama.check(),
        "obsidian": _obsidian.configured,
        "obsidian_desc": _obsidian.describe(),
        "voice": _voice.available,
        "voice_reason": _voice.reason,
        "voice_enabled": _voice.enabled,
        "tts_enabled": _voice.tts_enabled,
        "voice_mode": _assistant.voice_enabled,
    }


# ---------------------------------------------------------------------------
# Standalone runner (for development)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    print("Starting Local Assistant API...")
    print(f"Ollama: {_ollama.host} (model: {_ollama.model})")
    print(f"Obsidian: {_obsidian.describe()}")
    voice_status = "ready" if _voice.available else "unavailable"
    print(f"Voice: {voice_status}")
    print()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
