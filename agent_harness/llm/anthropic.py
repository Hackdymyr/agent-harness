"""Anthropic SDK adapter — converts between Anthropic content blocks and unified types."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from agent_harness.llm.retry import RetryConfig, with_retry
from agent_harness.types import (
    LLMResponse,
    Message,
    Role,
    StopReason,
    StreamEvent,
    ToolCall,
    ToolDefinition,
    ToolResultContent,
    Usage,
)

logger = logging.getLogger(__name__)


def _messages_to_anthropic(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert unified messages to Anthropic API format.

    Key differences:
    - Anthropic has no 'system' role in messages (system is a separate param)
    - tool_calls become content blocks of type 'tool_use'
    - tool results become content blocks of type 'tool_result' in a user message
    """
    result = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role", "user")

        if role == "system":
            i += 1
            continue

        if role == "assistant":
            content_blocks: list[dict[str, Any]] = []
            text = msg.get("content", "")
            if isinstance(text, str) and text:
                content_blocks.append({"type": "text", "text": text})
            elif isinstance(text, list):
                content_blocks.extend(text)

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    tc_data = tc if isinstance(tc, dict) else tc.model_dump()
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc_data["id"],
                        "name": tc_data["name"],
                        "input": tc_data.get("input", {}),
                    })

            result.append({"role": "assistant", "content": content_blocks or text})
            i += 1
            continue

        if role == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                result.append({"role": "user", "content": content})
            elif isinstance(content, list):
                # Check if these are tool results
                blocks: list[dict[str, Any]] = []
                for item in content:
                    if isinstance(item, dict) and "tool_use_id" in item:
                        blocks.append({
                            "type": "tool_result",
                            "tool_use_id": item["tool_use_id"],
                            "content": item.get("content", ""),
                            **({"is_error": True} if item.get("is_error") else {}),
                        })
                    else:
                        blocks.append(item)
                result.append({"role": "user", "content": blocks})
            i += 1
            continue

        # tool role (OpenAI-style) → merge into previous or create user message
        if role == "tool":
            tool_result_block = {
                "type": "tool_result",
                "tool_use_id": msg.get("tool_use_id", ""),
                "content": msg.get("content", ""),
                **({"is_error": True} if msg.get("is_error") else {}),
            }
            if result and result[-1]["role"] == "user" and isinstance(result[-1]["content"], list):
                result[-1]["content"].append(tool_result_block)
            else:
                result.append({"role": "user", "content": [tool_result_block]})
            i += 1
            continue

        result.append({"role": role, "content": msg.get("content", "")})
        i += 1

    return result


def _tools_to_anthropic(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert ToolDefinition list to Anthropic tool format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ]


def _parse_anthropic_response(response: Any) -> LLMResponse:
    """Parse Anthropic API response into unified LLMResponse."""
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(
                id=block.id,
                name=block.name,
                input=block.input,
            ))

    stop_map = {
        "end_turn": StopReason.END_TURN,
        "tool_use": StopReason.TOOL_USE,
        "max_tokens": StopReason.MAX_TOKENS,
    }

    return LLMResponse(
        message=Message(
            role=Role.ASSISTANT,
            content="\n".join(text_parts),
            tool_calls=tool_calls if tool_calls else None,
        ),
        stop_reason=stop_map.get(response.stop_reason, StopReason.END_TURN),
        usage=Usage(
            input_tokens=getattr(response.usage, "input_tokens", 0),
            output_tokens=getattr(response.usage, "output_tokens", 0),
        ),
    )


class AnthropicLLM:
    """Anthropic SDK adapter with retry support and real streaming."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 0,
        retry_config: RetryConfig | None = None,
    ):
        try:
            import anthropic
        except ImportError:
            raise ImportError("pip install anthropic")

        # SDK-level retries disabled; we use our own retry engine
        kwargs: dict[str, Any] = {"max_retries": max_retries}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.AsyncAnthropic(**kwargs)
        self.model = model
        self.retry_config = retry_config

    def _build_create_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None,
        system: str | None,
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        api_messages = _messages_to_anthropic(messages)
        create_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }
        if system:
            create_kwargs["system"] = system
        if tools:
            create_kwargs["tools"] = _tools_to_anthropic(tools)
        return create_kwargs

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        create_kwargs = self._build_create_kwargs(
            messages, tools, system, max_tokens, temperature, **kwargs
        )

        async def _call() -> LLMResponse:
            response = await self.client.messages.create(**create_kwargs)
            return _parse_anthropic_response(response)

        if self.retry_config:
            return await with_retry(_call, self.retry_config)
        return await _call()

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        create_kwargs = self._build_create_kwargs(
            messages, tools, system, max_tokens, temperature, **kwargs
        )

        # Track state for content blocks
        current_tool_id: dict[int, str] = {}   # index → tool_use id
        current_tool_name: dict[int, str] = {}  # index → tool name

        async with self.client.messages.stream(**create_kwargs) as stream:
            yield StreamEvent(type="message_start")

            async for event in stream:
                if event.type == "content_block_start":
                    idx = event.index
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool_id[idx] = block.id
                        current_tool_name[idx] = block.name
                    yield StreamEvent(type="content_block_start", index=idx)

                elif event.type == "content_block_delta":
                    idx = event.index
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield StreamEvent(type="text_delta", text=delta.text, index=idx)
                    elif delta.type == "input_json_delta":
                        yield StreamEvent(
                            type="tool_input_delta",
                            text=delta.partial_json,
                            index=idx,
                            tool_call_id=current_tool_id.get(idx),
                            tool_name=current_tool_name.get(idx),
                        )

                elif event.type == "content_block_stop":
                    yield StreamEvent(type="content_block_stop", index=event.index)

            # Get the final message for complete response
            final = await stream.get_final_message()
            parsed = _parse_anthropic_response(final)
            yield StreamEvent(
                type="message_done",
                stop_reason=parsed.stop_reason,
                usage=parsed.usage,
            )
