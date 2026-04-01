"""OpenAI SDK adapter — handles tool_calls field and tool-role messages."""

from __future__ import annotations

from typing import Any, AsyncIterator

from agent_harness.types import (
    LLMResponse,
    Message,
    Role,
    StopReason,
    ToolCall,
    ToolDefinition,
    Usage,
)


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
    import json

    return json.dumps(obj, ensure_ascii=False)


def _json_loads(s: str) -> Any:
    import json

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
    """OpenAI SDK adapter."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 2,
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

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
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

        response = await self.client.chat.completions.create(**create_kwargs)
        return _parse_openai_response(response)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponse]:
        # Simplified: collect full response then yield
        result = await self.chat(messages, tools, system, max_tokens, temperature, **kwargs)
        yield result
