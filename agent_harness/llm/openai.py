"""OpenAI SDK adapter — handles tool_calls field and tool-role messages."""

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
    Usage,
)

logger = logging.getLogger(__name__)


def _messages_to_openai(
    messages: list[dict[str, Any]], system: str | None = None
) -> list[dict[str, Any]]:
    """Convert unified messages to OpenAI API format.

    Key differences from Anthropic:
    - system is a regular message with role='system'
    - tool_calls are a separate field on the assistant message
    - tool results are separate messages with role='tool' + tool_call_id
    """
    result: list[dict[str, Any]] = []

    if system:
        result.append({"role": "system", "content": system})

    for msg in messages:
        role = msg.get("role", "user")

        if role == "system":
            result.append({"role": "system", "content": msg.get("content", "")})
            continue

        if role == "assistant":
            entry: dict[str, Any] = {"role": "assistant"}
            content = msg.get("content", "")
            if isinstance(content, str):
                entry["content"] = content
            else:
                entry["content"] = str(content)

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": (tc["id"] if isinstance(tc, dict) else tc.id),
                        "type": "function",
                        "function": {
                            "name": (tc["name"] if isinstance(tc, dict) else tc.name),
                            "arguments": _json_dumps(
                                tc["input"] if isinstance(tc, dict) else tc.input
                            ),
                        },
                    }
                    for tc in tool_calls
                ]
            result.append(entry)
            continue

        if role == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                # Check for tool results
                for item in content:
                    if isinstance(item, dict) and "tool_use_id" in item:
                        result.append({
                            "role": "tool",
                            "tool_call_id": item["tool_use_id"],
                            "content": item.get("content", ""),
                        })
                    else:
                        result.append({"role": "user", "content": str(item)})
            else:
                result.append({"role": "user", "content": content})
            continue

        if role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_use_id", msg.get("tool_call_id", "")),
                "content": msg.get("content", ""),
            })
            continue

        result.append({"role": role, "content": msg.get("content", "")})

    return result


def _tools_to_openai(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert ToolDefinition list to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(s: str) -> Any:
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_openai_response(response: Any) -> LLMResponse:
    """Parse OpenAI API response into unified LLMResponse."""
    choice = response.choices[0]
    msg = choice.message

    tool_calls: list[ToolCall] | None = None
    if msg.tool_calls:
        tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                input=_json_loads(tc.function.arguments),
            )
            for tc in msg.tool_calls
        ]

    finish_reason = choice.finish_reason or "stop"
    stop_map = {
        "stop": StopReason.END_TURN,
        "tool_calls": StopReason.TOOL_USE,
        "length": StopReason.MAX_TOKENS,
    }

    usage_obj = response.usage
    return LLMResponse(
        message=Message(
            role=Role.ASSISTANT,
            content=msg.content or "",
            tool_calls=tool_calls,
        ),
        stop_reason=stop_map.get(finish_reason, StopReason.END_TURN),
        usage=Usage(
            input_tokens=getattr(usage_obj, "prompt_tokens", 0) if usage_obj else 0,
            output_tokens=getattr(usage_obj, "completion_tokens", 0) if usage_obj else 0,
        ),
    )


class OpenAILLM:
    """OpenAI SDK adapter with retry support and streaming."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 0,
        retry_config: RetryConfig | None = None,
    ):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("pip install openai")

        kwargs: dict[str, Any] = {"max_retries": max_retries}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**kwargs)
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
        api_messages = _messages_to_openai(messages, system)
        create_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }
        if tools:
            create_kwargs["tools"] = _tools_to_openai(tools)
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
            response = await self.client.chat.completions.create(**create_kwargs)
            return _parse_openai_response(response)

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
        create_kwargs["stream"] = True
        create_kwargs["stream_options"] = {"include_usage": True}

        yield StreamEvent(type="message_start")

        # Accumulate state for building final response
        text_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}  # index → {id, name, arguments}
        finish_reason: str | None = None
        usage_input = 0
        usage_output = 0

        stream = await self.client.chat.completions.create(**create_kwargs)
        async for chunk in stream:
            if not chunk.choices and hasattr(chunk, "usage") and chunk.usage:
                # Final usage-only chunk (stream_options)
                usage_input = getattr(chunk.usage, "prompt_tokens", 0)
                usage_output = getattr(chunk.usage, "completion_tokens", 0)
                continue

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            fr = chunk.choices[0].finish_reason

            if fr:
                finish_reason = fr

            # Text delta
            if delta.content:
                text_parts.append(delta.content)
                yield StreamEvent(type="text_delta", text=delta.content)

            # Tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc_delta.id:
                        tool_calls_acc[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_acc[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments
                            yield StreamEvent(
                                type="tool_input_delta",
                                text=tc_delta.function.arguments,
                                index=idx,
                                tool_call_id=tool_calls_acc[idx]["id"],
                                tool_name=tool_calls_acc[idx]["name"],
                            )

        # Map finish_reason
        stop_map = {
            "stop": StopReason.END_TURN,
            "tool_calls": StopReason.TOOL_USE,
            "length": StopReason.MAX_TOKENS,
        }

        yield StreamEvent(
            type="message_done",
            stop_reason=stop_map.get(finish_reason or "stop", StopReason.END_TURN),
            usage=Usage(input_tokens=usage_input, output_tokens=usage_output),
        )
