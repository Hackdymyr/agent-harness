"""Token estimation utilities for context management.

Mirrors Claude Code's roughTokenCountEstimation() — uses a simple
chars-per-token heuristic (~4 chars/token for most text, ~2 for JSON).
"""

from __future__ import annotations

import json
from typing import Any


def rough_token_count(text: str, bytes_per_token: int = 4) -> int:
    """Estimate token count from text length.

    Mirrors Claude Code's roughTokenCountEstimation().
    Default ratio: ~4 characters per token for natural language.
    Use bytes_per_token=2 for dense JSON.
    """
    if not text:
        return 0
    return max(1, round(len(text) / bytes_per_token))


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """Estimate tokens for a single message dict.

    Handles both string content and structured content blocks
    (tool_result, tool_use, text blocks).
    """
    tokens = 0
    content = message.get("content", "")

    if isinstance(content, str):
        tokens += rough_token_count(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                tokens += rough_token_count(block)
            elif isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    tokens += rough_token_count(block.get("text", ""))
                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        tokens += rough_token_count(result_content)
                    elif isinstance(result_content, list):
                        for sub in result_content:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                tokens += rough_token_count(sub.get("text", ""))
                            elif isinstance(sub, dict) and sub.get("type") in ("image", "document"):
                                tokens += 2000  # Conservative flat estimate
                            else:
                                tokens += rough_token_count(json.dumps(sub))
                elif block_type == "tool_use":
                    tokens += rough_token_count(
                        block.get("name", "") + json.dumps(block.get("input", {}))
                    )
                elif block_type in ("image", "document"):
                    tokens += 2000
                else:
                    tokens += rough_token_count(json.dumps(block))
    else:
        tokens += rough_token_count(str(content))

    # Tool calls on assistant messages
    tool_calls = message.get("tool_calls", None)
    if tool_calls:
        for tc in tool_calls:
            if isinstance(tc, dict):
                tokens += rough_token_count(
                    tc.get("name", "") + json.dumps(tc.get("input", {}))
                )

    # Role overhead (~4 tokens per message for role/formatting)
    tokens += 4

    return tokens


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens across a list of messages."""
    return sum(estimate_message_tokens(m) for m in messages)
