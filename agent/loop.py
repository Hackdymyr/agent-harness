"""AgentLoop — the core engine. Mirrors query() from Claude Code's query.ts.

The loop cycle:
    messages → LLM call → parse tool_calls → execute tools → inject results → loop
    Stop when: stop_reason=end_turn AND no pending tool_use blocks
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Literal

from agent_harness.agent.context import AgentContext
from agent_harness.tools.orchestration import execute_tool_calls
from agent_harness.types import (
    LLMResponse,
    Message,
    Role,
    StopReason,
    ToolCall,
    ToolResultContent,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    """Yielded by the agent loop. Mirrors Claude Code's SDKMessage union."""

    type: Literal["message", "tool_call", "tool_result", "error", "done"]
    message: Message | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResultContent | None = None
    error: str | None = None
    usage: dict[str, int] | None = None


class AgentLoop:
    """The core agent engine.

    Mirrors the queryLoop() function from Claude Code's query.ts:
    - Stateful: maintains conversation in context.messages
    - AsyncGenerator: yields events as they happen
    - Recovery: handles max_tokens with retry
    - Context management: truncates when messages grow too long

    Usage:
        ctx = AgentContext(messages=[], tools=registry, llm=llm)
        loop = AgentLoop(ctx)

        async for event in loop.run("List all Python files"):
            if event.type == "message":
                print(event.message.content)
            elif event.type == "tool_result":
                print(f"Tool result: {event.tool_result.content[:100]}")
    """

    def __init__(
        self,
        context: AgentContext,
        on_tool_start: Callable[[ToolCall], None] | None = None,
        on_tool_end: Callable[[ToolCall, ToolResultContent], None] | None = None,
        max_context_messages: int | None = None,
    ):
        self.context = context
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.max_context_messages = max_context_messages

    async def run(
        self, user_input: str | list[dict[str, Any]]
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run the agent loop. Yields AgentEvent as they happen.

        Args:
            user_input: A string prompt, or a list of content blocks.
        """
        # Append user message
        if isinstance(user_input, str):
            self.context.messages.append(
                {"role": "user", "content": user_input}
            )
        else:
            self.context.messages.append(
                {"role": "user", "content": user_input}
            )

        turn_count = 0
        max_tokens_retries = 0

        while turn_count < self.context.max_turns:
            turn_count += 1

            # Abort check
            if self.context.is_aborted:
                yield AgentEvent(type="error", error="Agent aborted")
                return

            # Context window management
            messages_for_query = self._manage_context(self.context.messages)

            # Call LLM
            try:
                response: LLMResponse = await self.context.llm.chat(
                    messages=messages_for_query,
                    tools=self.context.tools.definitions() if len(self.context.tools) > 0 else None,
                    system=self.context.system_prompt,
                    max_tokens=self.context.max_tokens,
                    temperature=self.context.temperature,
                )
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                yield AgentEvent(type="error", error=f"LLM error: {e}")
                return

            # Append assistant message to conversation
            assistant_dict = {
                "role": "assistant",
                "content": response.message.content,
            }
            if response.message.tool_calls:
                assistant_dict["tool_calls"] = [
                    tc.model_dump() for tc in response.message.tool_calls
                ]
            self.context.messages.append(assistant_dict)

            # Yield assistant message event
            yield AgentEvent(
                type="message",
                message=response.message,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )

            # Handle tool calls
            if response.message.tool_calls:
                # Yield individual tool_call events
                for tc in response.message.tool_calls:
                    if self.on_tool_start:
                        self.on_tool_start(tc)
                    yield AgentEvent(type="tool_call", tool_call=tc)

                # Execute all tool calls with orchestration
                results = await execute_tool_calls(
                    response.message.tool_calls,
                    self.context.tools,
                    self.context,
                    self.context.permissions,
                )

                # Inject tool results as user message
                self.context.messages.append({
                    "role": "user",
                    "content": [r.model_dump() for r in results],
                })

                # Yield individual tool_result events
                for tc, result in zip(response.message.tool_calls, results):
                    if self.on_tool_end:
                        self.on_tool_end(tc, result)
                    yield AgentEvent(type="tool_result", tool_result=result)

                # Reset max_tokens retry counter on successful tool use
                max_tokens_retries = 0
                continue  # Next LLM call

            # No tool calls — check stop reason
            if response.stop_reason == StopReason.MAX_TOKENS:
                if max_tokens_retries < 3:
                    max_tokens_retries += 1
                    logger.info(
                        f"Max tokens hit, retry {max_tokens_retries}/3"
                    )
                    self.context.messages.append({
                        "role": "user",
                        "content": "Your response was cut off due to token limits. Please continue from where you left off.",
                    })
                    continue

            # Done — end_turn or exhausted retries
            yield AgentEvent(type="done")
            return

        # Exhausted max_turns
        yield AgentEvent(
            type="error",
            error=f"Agent reached maximum turns ({self.context.max_turns})",
        )

    async def run_to_completion(self, user_input: str) -> Message | None:
        """Convenience: run loop and return the final assistant message."""
        final: Message | None = None
        async for event in self.run(user_input):
            if event.type == "message" and event.message and event.message.role == Role.ASSISTANT:
                final = event.message
            elif event.type == "error":
                logger.error(f"Agent error: {event.error}")
        return final

    def _manage_context(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Truncate context if too many messages.

        Simple strategy: keep first message (often the initial user prompt)
        and the last N messages. Claude Code uses sophisticated compaction
        (summarization, microcompact, etc.) — we use truncation as the 80/20.
        """
        if self.max_context_messages is None:
            return messages

        if len(messages) <= self.max_context_messages:
            return messages

        # Keep first message + last (max_context_messages - 1) messages
        return [messages[0]] + messages[-(self.max_context_messages - 1):]
