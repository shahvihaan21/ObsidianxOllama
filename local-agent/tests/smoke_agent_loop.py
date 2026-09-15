"""Smoke test for Agent Loop."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import Config
from agent.ollama_client import OllamaClient
from agent.permissions import PermissionManager
from tools.registry import build_registry
from agent.loop import AgentLoop

def cli_asker(prompt_text: str) -> str:
    print(f"Auto-confirming test prompt: {prompt_text}")
    return "yes"

def main():
    config = Config.load()
    client = OllamaClient(host=config.ollama.host, model="qwen3:1.7b")
    registry = build_registry()
    permissions = PermissionManager(config=config, registry=registry, asker=cli_asker)
    
    loop = AgentLoop(config=config, client=client, registry=registry, permissions=permissions)
    
    print("Testing Agent Loop: 'What is 2+2?'")
    resp = loop.run("What is 2+2? Answer simply.")
    print("Agent Response:", resp)
    assert "4" in resp or "four" in resp.lower(), "Response didn't contain 4"
    print("OK")
    
    print("Testing Tool Execution: 'Open Notepad'")
    resp = loop.run("Open Notepad")
    print("Agent Response:", resp)
    print("OK")

if __name__ == "__main__":
    main()
