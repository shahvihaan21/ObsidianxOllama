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

    def _enforce_limits(self) -> None:
        """Enforce max_history_messages and max_context_chars on self.history.

        Preserves any initial system prompt(s) and keeps the most recent relevant
        turns so that neither message count nor character limits are silently exceeded.
        """
        if not self.history:
            return

        max_messages = getattr(self.config.agent, "max_history_messages", 24)
        max_chars = getattr(self.config.agent, "max_context_chars", 24000)

        # Separate system messages (which should be preserved at front if present)
        system_msgs: list[ChatMessage] = []
        conversation_msgs: list[ChatMessage] = []

        for m in self.history:
            if m.role == "system":
                system_msgs.append(m)
            else:
                conversation_msgs.append(m)

        # 1. Enforce message count limit on conversation messages
        allowed_conv_count = max(1, max_messages - len(system_msgs))
        if len(conversation_msgs) > allowed_conv_count:
            conversation_msgs = conversation_msgs[-allowed_conv_count:]

        # 2. Enforce character count limit
        def message_len(m: ChatMessage) -> int:
            length = len(m.content or "")
            if m.tool_name:
                length += len(m.tool_name)
            for tc in m.tool_calls:
                length += len(tc.name) + len(str(tc.arguments))
            return length

        sys_chars = sum(message_len(m) for m in system_msgs)
        allowed_chars = max(0, max_chars - sys_chars)

        trimmed_conv: list[ChatMessage] = []
        current_chars = 0
        for m in reversed(conversation_msgs):
            m_len = message_len(m)
            if trimmed_conv and (current_chars + m_len > allowed_chars):
                break
            trimmed_conv.append(m)
            current_chars += m_len

        trimmed_conv.reverse()
        self.history = system_msgs + trimmed_conv

    def run(self, user_prompt: str) -> str:
        """Run the agent loop for a user request."""
        self.history.append(ChatMessage.user(user_prompt))

        max_steps = self.config.agent.max_steps
        step = 0

        self.on_event("THINKING", {})

        while step < max_steps:
            step += 1
            log.info("Agent loop step %d/%d", step, max_steps)
            self._enforce_limits()

            # 1. Ask Ollama
            try:
                temp = getattr(self.config.agent, "temperature", 0.3)
                response = self.client.chat(
                    self.history,
                    tools=self.registry.schemas(),
                    temperature=temp,
                )
            except Exception as e:
                log.error("Ollama error: %s", e)
                return f"Error connecting to Ollama: {e}"
            
            self.history.append(response.message)
            
            # 2. Check if no tool calls -> return response
            if not response.message.tool_calls:
                return response.message.content or "No response from model."
            
            # 3. Process tool calls
            has_denial_or_error = False
            last_error_message = ""

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
                        has_denial_or_error = True
                        last_error_message = result
                    else:
                        # 5. Execute
                        tool_result = self.registry.execute(tool_name, args)
                        result = tool_result.to_json()
                except Exception as e:
                    result = f"Error executing {tool_name}: {e}"
                    has_denial_or_error = True
                    last_error_message = result

                # Append tool result to history
                self.history.append(ChatMessage.tool_result(tc.name, result))

            # If a dangerous/destructive tool was denied or failed fatally, we can return immediately
            if has_denial_or_error:
                return last_error_message
            
            self.on_event("THINKING", {})

        return "Error: Maximum steps reached without final response."
