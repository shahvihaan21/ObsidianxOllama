"""Unit and integration tests for tools and configuration."""

import os
import tempfile
from pathlib import Path
import pytest

from agent.config import Config
from agent.loop import AgentLoop
from agent.ollama_client import ChatMessage, ToolCall
from agent.permissions import PermissionManager
from tools.registry import build_registry, Level


class FakeClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, tools=None, temperature=None):
        self.calls.append((messages, tools, temperature))
        return type("Resp", (), {"message": ChatMessage.assistant("Done")})()


def test_config_defaults_and_env():
    config = Config.load()
    assert config.ollama.host == "http://127.0.0.1:11434"
    assert config.ollama.model == "qwen3:1.7b"
    assert config.agent.max_history_messages == 24
    assert config.agent.max_context_chars == 24000
    assert config.agent.temperature == 0.3


def test_history_and_context_trimming():
    config = Config.load()
    config.agent.max_history_messages = 4
    config.agent.max_context_chars = 100

    client = FakeClient()
    registry = build_registry()
    perms = PermissionManager(config=config, registry=registry)
    loop = AgentLoop(config=config, client=client, registry=registry, permissions=perms)

    loop.history = [
        ChatMessage.system("System prompt."),
        ChatMessage.user("A" * 50),
        ChatMessage.assistant("B" * 50),
        ChatMessage.user("C" * 50),
        ChatMessage.assistant("D" * 50),
    ]

    loop._enforce_limits()
    # Ensure system prompt is preserved
    assert loop.history[0].role == "system"
    # Ensure count limit and char limit are respected
    assert len(loop.history) <= 4
    total_chars = sum(len(m.content) for m in loop.history)
    assert total_chars <= 150  # within bounded range


def test_filesystem_tools():
    registry = build_registry()
    assert registry.has("read_file")
    assert registry.has("write_file")
    assert registry.has("list_files")
    assert registry.has("delete_file")

    with tempfile.TemporaryDirectory() as td:
        test_file = Path(td) / "test.txt"
        
        # Test write
        res_write = registry.execute("write_file", {"path": str(test_file), "content": "hello obsidian"})
        assert res_write.success
        assert test_file.exists()

        # Test read
        res_read = registry.execute("read_file", {"path": str(test_file)})
        assert res_read.success
        assert "hello obsidian" in res_read.result

        # Test list
        res_list = registry.execute("list_files", {"path": td})
        assert res_list.success
        assert "test.txt" in res_list.result

        # Test delete
        res_del = registry.execute("delete_file", {"path": str(test_file)})
        assert res_del.success
        assert not test_file.exists()


def test_obsidian_tools():
    registry = build_registry()
    assert registry.has("search_memory")
    assert registry.has("read_obsidian_note")
    assert registry.has("create_obsidian_note")
    assert registry.has("append_obsidian_note")

    with tempfile.TemporaryDirectory() as td:
        os.environ["LOCALAGENT_VAULT"] = td
        
        # Create note
        res_create = registry.execute("create_obsidian_note", {"name": "project.md", "content": "# Project Roadmap"})
        assert res_create.success

        # Read note
        res_read = registry.execute("read_obsidian_note", {"name": "project.md"})
        assert res_read.success
        assert "Project Roadmap" in res_read.result

        # Append note
        res_append = registry.execute("append_obsidian_note", {"name": "project.md", "content": "- Milestone 1"})
        assert res_append.success

        # Read appended note
        res_read2 = registry.execute("read_obsidian_note", {"name": "project.md"})
        assert "- Milestone 1" in res_read2.result

        # Search memory
        res_search = registry.execute("search_memory", {"query": "Milestone"})
        assert res_search.success
        assert "project.md" in res_search.result


def test_browser_tools():
    registry = build_registry()
    assert registry.has("open_url")
    assert registry.has("search_web")
    assert registry.has("new_tab")
    assert registry.has("close_tab")
    assert registry.has("read_webpage")
