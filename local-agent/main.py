import logging
import sys
import os
from pathlib import Path
from agent.config import Config
from agent.ollama_client import OllamaClient
from agent.permissions import PermissionManager
from tools.registry import build_registry
from agent.loop import AgentLoop

log_dir = Path(__file__).resolve().parent / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "agent.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

def cli_asker(prompt_text: str) -> str:
    print("\n" + "="*40)
    print(prompt_text)
    print("="*40)
    return input("Answer: ")

def main():
    config = Config.load()
    client = OllamaClient(host=config.ollama.host, model=config.ollama.model)
    registry = build_registry()
    permissions = PermissionManager(config=config, registry=registry, asker=cli_asker)
    
    loop = AgentLoop(config=config, client=client, registry=registry, permissions=permissions)
    
    print(f"Agent started. Model: {config.ollama.model}")
    while True:
        try:
            req = input("\nUser: ")
            if not req.strip():
                continue
            if req.strip().lower() in ["exit", "quit"]:
                break
            
            resp = loop.run(req)
            print(f"\nAgent: {resp}")
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    main()
