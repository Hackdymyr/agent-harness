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
