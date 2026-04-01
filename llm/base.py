"""BaseLLM Protocol — the abstraction layer Claude Code lacks."""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from agent_harness.types import LLMResponse, ToolDefinition


@runtime_checkable
class BaseLLM(Protocol):
    """Unified interface for any LLM provider.

    Implementations must convert between their native format and the
    agent_harness Message/ToolCall types.
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
    ) -> AsyncIterator[LLMResponse]:
        """Streaming variant. Final yield contains the complete message."""
        ...
