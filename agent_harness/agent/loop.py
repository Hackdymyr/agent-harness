"""AgentLoop — the core engine. Mirrors query() from Claude Code's query.ts.

The loop cycle:
    messages → LLM call → parse tool_calls → execute tools → inject results → loop
    Stop when: stop_reason=end_turn AND no pending tool_use blocks
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Literal

from agent_harness.agent.context import AgentContext
from agent_harness.compact.auto_compact import AutoCompactState, auto_compact_if_needed
from agent_harness.compact.compactor import CompactConfig
from agent_harness.tools.orchestration import execute_tool_calls
from agent_harness.types import (
    LLMResponse,
    Message,
    Role,
    StopReason,
    StreamEvent,
    ToolCall,
    ToolResultContent,
    Usage,
)

logger = logging.getLogger(__name__)

# Default idle timeout for streaming: abort if no chunks for this many seconds
STREAM_IDLE_TIMEOUT_S = 90


@dataclass
class AgentEvent:
    """Yielded by the agent loop. Mirrors Claude Code's SDKMessage union."""

    type: Literal["message", "tool_call", "tool_result", "stream_delta", "compaction", "error", "done"]
    message: Message | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResultContent | None = None
    stream_event: StreamEvent | None = None
    error: str | None = None
    usage: dict[str, int] | None = None


class AgentLoop:
    """The core agent engine.

    Mirrors the queryLoop() function from Claude Code's query.ts:
    - Stateful: maintains conversation in context.messages
    - AsyncGenerator: yields events as they happen
    - Recovery: handles max_tokens with retry
    - Context management: auto compaction (LLM summary) + micro compaction + truncation fallback
    - Streaming: optional real-time token streaming via streaming=True

    Usage:
        ctx = AgentContext(messages=[], tools=registry, llm=llm)
        loop = AgentLoop(ctx)

        async for event in loop.run("List all Python files"):
            if event.type == "message":
                print(event.message.content)
            elif event.type == "stream_delta":
                print(event.stream_event.text, end="", flush=True)
            elif event.type == "tool_result":
                print(f"Tool result: {event.tool_result.content[:100]}")
    """

    def __init__(
        self,
        context: AgentContext,
        on_tool_start: Callable[[ToolCall], None] | None = None,
        on_tool_end: Callable[[ToolCall, ToolResultContent], None] | None = None,
        max_context_messages: int | None = None,
        streaming: bool = False,
        stream_idle_timeout: float = STREAM_IDLE_TIMEOUT_S,
        compact_config: CompactConfig | None = None,
        enable_auto_compact: bool = True,
    ):
        self.context = context
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.max_context_messages = max_context_messages
        self.streaming = streaming
        self.stream_idle_timeout = stream_idle_timeout
        self.compact_config = compact_config
        self.enable_auto_compact = enable_auto_compact
        self._auto_compact_state = AutoCompactState()

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
        self._pending_compaction_event = None

        while turn_count < self.context.max_turns:
            turn_count += 1

            # Abort check
            if self.context.is_aborted:
                yield AgentEvent(type="error", error="Agent aborted")
                return

            # Context window management (may trigger compaction)
            messages_for_query = await self._manage_context(self.context.messages)

            # Yield compaction event if compaction occurred
            if self._pending_compaction_event is not None:
                result = self._pending_compaction_event
                self._pending_compaction_event = None
                yield AgentEvent(
                    type="compaction",
                    message=Message(
                        role=Role.SYSTEM,
                        content=(
                            f"[Compaction: {result.pre_compact_tokens} -> "
                            f"{result.post_compact_tokens} estimated tokens]"
                        ),
                    ),
                )

            # Call LLM (streaming or batch)
            try:
                if self.streaming:
                    response = await self._call_streaming(messages_for_query)
                    # _call_streaming handles yielding stream events internally,
                    # but we can't yield from a helper in an async generator.
                    # Instead, we do it inline.
                    response = None  # Will be set below

                    # Streaming path: yield deltas, accumulate final response
                    llm_kwargs = self._build_llm_kwargs(messages_for_query)
                    text_acc: list[str] = []
                    tool_inputs: dict[int, dict[str, Any]] = {}
                    final_stop_reason = StopReason.END_TURN
                    final_usage = Usage()

                    stream = self.context.llm.chat_stream(**llm_kwargs)
                    async for event in _stream_with_watchdog(stream, self.stream_idle_timeout):
                        if event.type == "text_delta" and event.text:
                            text_acc.append(event.text)
                            yield AgentEvent(type="stream_delta", stream_event=event)

                        elif event.type == "tool_input_delta":
                            idx = event.index or 0
                            if idx not in tool_inputs:
                                tool_inputs[idx] = {
                                    "id": event.tool_call_id or "",
                                    "name": event.tool_name or "",
                                    "arguments": "",
                                }
                            if event.text:
                                tool_inputs[idx]["arguments"] += event.text
                            yield AgentEvent(type="stream_delta", stream_event=event)

                        elif event.type == "message_done":
                            if event.stop_reason:
                                final_stop_reason = event.stop_reason
                            if event.usage:
                                final_usage = event.usage

                    # Build tool_calls from accumulated data
                    tool_calls: list[ToolCall] | None = None
                    if tool_inputs:
                        tool_calls = []
                        for idx in sorted(tool_inputs.keys()):
                            ti = tool_inputs[idx]
                            try:
                                parsed_input = json.loads(ti["arguments"]) if ti["arguments"] else {}
                            except json.JSONDecodeError:
                                parsed_input = {}
                            tool_calls.append(ToolCall(
                                id=ti["id"],
                                name=ti["name"],
                                input=parsed_input,
                            ))

                    response = LLMResponse(
                        message=Message(
                            role=Role.ASSISTANT,
                            content="".join(text_acc),
                            tool_calls=tool_calls if tool_calls else None,
                        ),
                        stop_reason=final_stop_reason,
                        usage=final_usage,
                    )

                else:
                    # Non-streaming path (original behavior)
                    response = await self.context.llm.chat(
                        **self._build_llm_kwargs(messages_for_query)
                    )

            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                yield AgentEvent(type="error", error=f"LLM error: {e}")
                return

            # Append assistant message to conversation
            assistant_dict: dict[str, Any] = {
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

    def _build_llm_kwargs(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Build keyword arguments for LLM chat/chat_stream calls."""
        kwargs: dict[str, Any] = {
            "messages": messages,
            "system": self.context.resolve_system_prompt(),
            "max_tokens": self.context.max_tokens,
            "temperature": self.context.temperature,
        }
        if len(self.context.tools) > 0:
            kwargs["tools"] = self.context.tools.definitions()
        return kwargs

    async def run_to_completion(self, user_input: str) -> Message | None:
        """Convenience: run loop and return the final assistant message."""
        final: Message | None = None
        async for event in self.run(user_input):
            if event.type == "message" and event.message and event.message.role == Role.ASSISTANT:
                final = event.message
            elif event.type == "error":
                logger.error(f"Agent error: {event.error}")
        return final

    async def _manage_context(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Manage context window with compaction support.

        Strategy (mirrors Claude Code's query.ts execution order):
        1. Auto compact (LLM summary) if enabled and threshold exceeded
        2. Fall back to simple truncation if max_context_messages is set

        When auto compaction runs successfully, it replaces context.messages
        in-place and yields a compaction event.
        """
        # Auto compaction (LLM-based)
        if self.enable_auto_compact:
            config = self.compact_config or CompactConfig(
                context_window=self.context.context_window
            )
            result = await auto_compact_if_needed(
                messages,
                self.context.llm,
                config,
                self._auto_compact_state,
            )
            if result and result.was_compacted:
                self.context.messages[:] = result.messages
                self._pending_compaction_event = result
                return result.messages

        # Fallback: simple truncation
        if self.max_context_messages is not None and len(messages) > self.max_context_messages:
            return [messages[0]] + messages[-(self.max_context_messages - 1):]

        return messages


async def _stream_with_watchdog(
    stream: Any,
    timeout: float = STREAM_IDLE_TIMEOUT_S,
) -> AsyncGenerator[StreamEvent, None]:
    """Wrap an async iterator with an idle timeout watchdog.

    If no events arrive within `timeout` seconds, raises asyncio.TimeoutError.
    This prevents hanging on stalled connections (mirrors Claude Code's 90s watchdog).
    """
    aiter = stream.__aiter__()
    while True:
        try:
            event = await asyncio.wait_for(aiter.__anext__(), timeout=timeout)
            yield event
        except StopAsyncIteration:
            return
        except asyncio.TimeoutError:
            logger.error(f"Stream idle timeout ({timeout}s) — aborting")
            raise
