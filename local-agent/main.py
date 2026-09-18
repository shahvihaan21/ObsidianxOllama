"""Entry point: wires config.json, Ollama, tools, Obsidian, voice and the loop.

    python main.py

Press Enter instead of typing to talk. Type 'quit' to exit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core import Assistant, default_confirm
from obsidian import Obsidian
from ollama import Ollama
from tools import Tools
from voice import Voice

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

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
    """Read config.json next to this file; fall back to defaults per section."""
    config = {section: dict(values) for section, values in DEFAULT_CONFIG.items()}
    file_path = Path(path) if path else CONFIG_PATH
    if not file_path.is_file():
        print(f"No config file at {file_path}; using built-in defaults.")
        return config
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Config at {file_path} could not be read ({exc}); using defaults.")
        return config
    for section, values in config.items():
        if isinstance(raw.get(section), dict):
            values.update(raw[section])
    return config


def startup_status(ollama: Ollama, obsidian: Obsidian, voice: Voice) -> str:
    """The short banner printed before the first prompt."""
    ollama_state = (
        "connected"
        if ollama.is_available()
        else "not connected (start Ollama and try again)"
    )
    obsidian_state = "configured" if obsidian.configured else "not configured"
    voice_state = "ready" if voice.available else f"unavailable ({voice.reason})"
    return "\n".join(
        [
            "================================",
            "       Local Assistant",
            "================================",
            "",
            f"Ollama: {ollama_state}",
            f"Model: {ollama.model}",
            f"Obsidian: {obsidian_state}",
            f"Voice: {voice_state}",
        ]
    )


def run_loop(assistant: Assistant, voice: Voice) -> None:
    """Read one request at a time. Never exits because of a failed command."""
    while True:
        try:
            raw = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return

        text = raw.strip()
        if text.lower() in {"quit", "exit", "q"}:
            print("Goodbye.")
            return

        spoken = False
        if not text:
            if not voice.available:
                print(f"Voice is unavailable ({voice.reason}). Type a command instead.")
                continue
            print("Listening...")
            text = voice.listen().strip()
            if not text:
                print("I couldn't understand that.")
                continue
            print(f"You said: {text}")
            spoken = True

        try:
            response = assistant.handle(text)
        except Exception as exc:  # noqa: BLE001 - one bad command must not end the session
            response = f"Something went wrong: {exc}"

        if not response:
            continue

        print(f"\n{response}")
        if spoken and voice.tts_enabled:
            # A failed TTS call only logs; the answer is already printed above.
            voice.speak(response)


def main() -> int:
    config = load_config()

    ollama = Ollama(
        host=config["ollama"]["host"],
        model=config["ollama"]["model"],
        timeout=config["ollama"]["timeout"],
    )
    obsidian = Obsidian(
        vault=config["obsidian"]["vault"],
        max_results=config["obsidian"]["max_results"],
    )
    voice = Voice(voice_config=config["voice"], tts_config=config["tts"])
    assistant = Assistant(
        ollama=ollama, tools=Tools(obsidian=obsidian), confirm=default_confirm
    )

    print(startup_status(ollama, obsidian, voice))
    print()
    print("Assistant ready.")
    print()
    print("Type a command or press Enter for voice.")
    print("Type 'quit' to exit.")

    try:
        run_loop(assistant, voice)
    except KeyboardInterrupt:
        print("\nGoodbye.")
    finally:
        voice.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
