import logging
import sys
import os
from pathlib import Path
from agent.config import Config
from agent.ollama_client import OllamaClient
from agent.permissions import PermissionManager
from tools.registry import build_registry
from agent.loop import AgentLoop

from visualizer.app import write_bus_state, start_visualizer
import threading

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
    client = OllamaClient(
        host=config.ollama.host,
        model=config.ollama.model,
        timeout=config.agent.request_timeout,
        max_retries=config.agent.max_retries,
        num_ctx=config.ollama.num_ctx,
        keep_alive=config.ollama.keep_alive,
        think=config.ollama.think,
        temperature=config.agent.temperature,
    )
    registry = build_registry(tool_result_max_chars=config.agent.tool_result_max_chars)
    permissions = PermissionManager(config=config, registry=registry, asker=cli_asker)

    def on_agent_event(event_name: str, data: Any) -> None:
        write_bus_state(event_name, data if isinstance(data, dict) else {"data": data})

    loop = AgentLoop(
        config=config,
        client=client,
        registry=registry,
        permissions=permissions,
        on_event=on_agent_event,
    )

    # Start visualizer server if enabled in config
    if config.visualizer.enabled and config.visualizer.serve:
        vis_thread = threading.Thread(
            target=start_visualizer,
            kwargs={"port": config.visualizer.port},
            daemon=True,
        )
        vis_thread.start()
        print(f"Visualizer running at http://127.0.0.1:{config.visualizer.port}")
    
    from voice.loop import VoiceLoop
    if config.voice.enabled:
        voice_loop = VoiceLoop(config=config, agent_loop=loop)
        voice_thread = threading.Thread(target=voice_loop.start, daemon=True)
        voice_thread.start()
        print(f"Voice enabled. PTT Key: {config.voice.ptt_key}")

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
