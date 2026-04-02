"""Shared types for agent_harness — the lingua franca between LLM providers and tools."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"  # OpenAI-style tool result role


class StopReason(str, Enum):
    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"
    ERROR = "error"


class ToolCall(BaseModel):
    """Normalized tool_use block from any LLM provider."""

    id: str = Field(default_factory=lambda: f"call_{uuid4().hex[:12]}")
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultContent(BaseModel):
    """Normalized tool_result to feed back to the LLM."""

    tool_use_id: str
    content: str
    is_error: bool = False


class Message(BaseModel):
    """Provider-agnostic message."""

    role: Role
    content: str | list[Any] = ""
    tool_calls: list[ToolCall] | None = None
    tool_use_id: str | None = None  # For tool result messages (OpenAI style)
    name: str | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMResponse(BaseModel):
    """What BaseLLM.chat() returns."""

    message: Message
    stop_reason: StopReason = StopReason.END_TURN
    usage: Usage = Field(default_factory=Usage)


class ToolDefinition(BaseModel):
    """JSON Schema representation sent to LLM APIs."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class StreamEvent(BaseModel):
    """Event yielded during streaming LLM responses.

    Different event types carry different fields:
    - text_delta: incremental text, carries `text`
    - tool_input_delta: incremental tool JSON, carries `text` (partial JSON) and `index`
    - message_start: beginning of response, may carry `usage`
    - message_done: end of response, carries `stop_reason` and `usage`
    - content_block_start: start of a content block, carries `index`
    - content_block_stop: end of a content block, carries `index`
    """

    type: str  # text_delta, tool_input_delta, message_start, message_done, etc.
    text: str | None = None
    index: int | None = None
    usage: Usage | None = None
    stop_reason: StopReason | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
