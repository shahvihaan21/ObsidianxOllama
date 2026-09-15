"""Agent execution loop.

Coordinates the LLM, permissions, and tool execution.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from agent.config import Config
from agent.ollama_client import ChatMessage, OllamaClient
from agent.permissions import PermissionManager
from tools.registry import ToolRegistry

log = logging.getLogger(__name__)


class AgentLoop:
    """The core agent loop execution."""

    def __init__(
        self,
        config: Config,
        client: OllamaClient,
        registry: ToolRegistry,
        permissions: PermissionManager,
        on_event: Callable[[str, Any], None] | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.registry = registry
        self.permissions = permissions
        self.on_event = on_event or (lambda ev, data: None)
        self.history: list[ChatMessage] = []

    def run(self, user_prompt: str) -> str:
        """Run the agent loop for a user request."""
        self.history.append(ChatMessage.user(user_prompt))
        
        max_steps = self.config.agent.max_steps
        step = 0

        self.on_event("THINKING", {})
        
        while step < max_steps:
            step += 1
            log.info("Agent loop step %d/%d", step, max_steps)
            
            # 1. Ask Ollama
            try:
                response = self.client.chat(self.history, tools=self.registry.schemas())
            except Exception as e:
                log.error("Ollama error: %s", e)
                return f"Error connecting to Ollama: {e}"
            
            self.history.append(response.message)
            
            # 2. Check if no tool calls -> return response
            if not response.message.tool_calls:
                return response.message.content or "No response from model."
            
            # 3. Process tool calls
            for tc in response.message.tool_calls:
                tool_name = tc.name
                args = tc.arguments
                
                self.on_event("EXECUTING", {"tool": tool_name, "args": args})
                
                try:
                    tool = self.registry.get(tool_name)
                    # 4. Check permissions
                    verdict = self.permissions.request(tool, args)
                    if not verdict.allowed:
                        result = f"Permission denied: {verdict.reason}"
                    else:
                        # 5. Execute
                        tool_result = self.registry.execute(tool_name, args)
                        result = tool_result.to_json()
                except Exception as e:
                    result = f"Error executing {tool_name}: {e}"
                
                # Append tool result to history
                self.history.append(ChatMessage.tool_result(tc.name, result))
            
            self.on_event("THINKING", {})

        return "Error: Maximum steps reached without final response."
