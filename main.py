"""Local AI Assistant — CLI entry point.

Run:
    python main.py

No web server, no browser, no frontend required.
"""

from __future__ import annotations

import logging
import sys

# ---------------------------------------------------------------------------
# Logging: info+ goes to stderr so the clean conversation is on stdout.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s: %(message)s",
    stream=sys.stderr,
)

from local_agent import config as _config_mod
from local_agent.assistant import Assistant, default_confirm
from local_agent.cli import run
from local_agent.llm import Ollama
from local_agent.obsidian import Obsidian
from local_agent.tools import Tools
from local_agent.voice import Voice


def _status_text(ollama: Ollama, obsidian: Obsidian, voice: Voice) -> str:
    """One-line status for each subsystem, printed at startup."""
    lines = []

    ollama_ok = ollama.is_available()
    if ollama_ok:
        lines.append(f"Ollama    connected  (model: {ollama.model})")
    else:
        lines.append(f"Ollama    NOT reachable at {ollama.host}")

    if obsidian.configured:
        lines.append(f"Obsidian  configured  ({obsidian.vault})")
    else:
        lines.append("Obsidian  not configured  (set VAULT_PATH or obsidian.vault in config.json)")

    if voice.available:
        lines.append("Voice     ready")
    else:
        lines.append(f"Voice     unavailable  ({voice.reason})")

    return "\n".join(f"  {line}" for line in lines)


def main() -> None:
    # ---- Load config -------------------------------------------------------
    cfg = _config_mod.load()

    # ---- Build components --------------------------------------------------
    ollama = Ollama(
        host=cfg["ollama"]["host"],
        model=cfg["ollama"]["model"],
        timeout=cfg["ollama"]["timeout"],
    )
    obsidian = Obsidian(
        vault=cfg["obsidian"]["vault"],
        max_results=cfg["obsidian"]["max_results"],
    )
    voice = Voice(
        voice_config=cfg["voice"],
        tts_config=cfg["tts"],
    )
    tools = Tools(obsidian=obsidian)
    assistant = Assistant(
        ollama=ollama,
        tools=tools,
        confirm=default_confirm,
        voice=voice,
    )

    # ---- Startup status ---------------------------------------------------
    print()
    print(_status_text(ollama, obsidian, voice))
    print()

    # ---- Warn if Ollama is unreachable ------------------------------------
    if not ollama.is_available():
        print(
            "[Warning] Ollama is not running. Start Ollama and the model will be used "
            "when it becomes available.\n"
            "          Run:  ollama serve\n"
            "          Then: ollama pull " + ollama.model
        )
        print()

    # ---- Enter the interactive loop ---------------------------------------
    run(assistant)


if __name__ == "__main__":
    main()
