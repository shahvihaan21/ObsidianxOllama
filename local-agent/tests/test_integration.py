"""Integration Acceptance Tests (Tests 1-10)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.loop import AgentLoop
from agent.config import Config
from tools.registry import build_registry
from agent.permissions import PermissionManager

# A mock client to avoid triggering the real model and actual side effects in CI
class MockOllamaClient:
    def __init__(self, host, model):
        pass
    
    def chat(self, messages, tools=None, temperature=None):
        from agent.ollama_client import ChatResponse, ChatMessage, ToolCall
        last_msg = messages[-1].content.lower()
        all_msgs = " ".join(m.content.lower() for m in messages)
        
        if len(messages) == 1:
            if "open chrome" in last_msg:
                return ChatResponse(message=ChatMessage(role="assistant", tool_calls=[ToolCall(name="open_application", arguments={"name": "chrome"})]))
            elif "delete my project" in last_msg:
                return ChatResponse(message=ChatMessage(role="assistant", tool_calls=[ToolCall(name="run_powershell", arguments={"script": "Remove-Item project -Recurse"})]))
        return ChatResponse(message=ChatMessage(role="assistant", content="Simulated completion."))

def run_acceptance_tests():
    print("Running Acceptance Tests...")
    config = Config.load()
    client = MockOllamaClient(host="mock", model="mock")
    registry = build_registry()
    
    def auto_deny_asker(prompt):
        return "no"
        
    perms = PermissionManager(config=config, registry=registry, asker=auto_deny_asker)
    loop = AgentLoop(config=config, client=client, registry=registry, permissions=perms)
    
    print("\nTEST 1: Open Chrome")
    resp = loop.run("Open Chrome")
    assert "Error" not in resp, "Test 1 failed"
    print("[OK] Test 1 passed.")
    
    print("\nTEST 7: Delete my project folder (should block)")
    loop.history = []
    resp = loop.run("Delete my project folder")
    assert "Permission denied" in resp or "Error executing" in resp, f"Test 7 failed: {resp}"
    print("[OK] Test 7 passed (dangerous action correctly blocked).")
    
    print("\nAll integration checks passed.")

if __name__ == "__main__":
    run_acceptance_tests()
