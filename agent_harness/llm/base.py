"""BaseLLM Protocol — the abstraction layer for any LLM provider.

Defines two calling modes:
- chat(): Single-shot completion (returns complete LLMResponse)
- chat_stream(): Streaming completion (yields StreamEvent, final yield has stop_reason)
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from agent_harness.types import LLMResponse, StreamEvent, ToolDefinition


@runtime_checkable
class BaseLLM(Protocol):
    """Unified interface for any LLM provider.

    Implementations must convert between their native format and the
    agent_harness Message/ToolCall types.

    Both chat() and chat_stream() should support optional retry via
    the RetryConfig from agent_harness.llm.retry.
    """

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        """Single-shot completion with optional tool definitions."""
        ...

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Streaming completion. Yields StreamEvent objects.

        The final event has type="message_done" with stop_reason and usage.
        Callers can accumulate text_delta events to build the full response,
        or use chat() if they just need the final result.

        Default implementation: calls chat() and yields a single message_done event.
        """
        ...
