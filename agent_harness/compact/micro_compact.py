"""Micro compaction — clear old tool results without LLM involvement.

Mirrors Claude Code's microcompactMessages() from microCompact.ts.
Replaces the content of old tool results with a short placeholder,
keeping only the N most recent tool results intact.
"""

from __future__ import annotations

import copy
from typing import Any

from agent_harness.compact.token_estimation import rough_token_count

CLEARED_MESSAGE = "[Old tool result content cleared]"

DEFAULT_COMPACTABLE_TOOLS: set[str] = {
    "read_file",
    "bash",
    "grep",
    "glob",
    "web_search",
    "web_fetch",
    "edit_file",
    "write_file",
}


def micro_compact(
    messages: list[dict[str, Any]],
    keep_last_n: int = 5,
    compactable_tools: set[str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Replace old tool result contents with a placeholder.

    Walks messages backwards, preserves the last `keep_last_n` tool results,
    and clears older ones for compactable tools.

    Args:
        messages: Conversation messages (not mutated).
        keep_last_n: Number of most-recent tool results to keep intact.
        compactable_tools: Tool names whose results can be cleared.
            Defaults to DEFAULT_COMPACTABLE_TOOLS.

    Returns:
        (compacted_messages, tokens_saved): New message list and estimated tokens freed.
    """
    if compactable_tools is None:
        compactable_tools = DEFAULT_COMPACTABLE_TOOLS

    # Collect all tool_use IDs from compactable tools, newest first
    tool_use_ids: list[str] = []
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                if isinstance(tc, dict) and tc.get("name") in compactable_tools:
                    tool_use_ids.append(tc.get("id", ""))

    # IDs to keep (the most recent N)
    keep_ids = set(tool_use_ids[:keep_last_n])
    # IDs to clear
    clear_ids = set(tool_use_ids[keep_last_n:])

    if not clear_ids:
        return messages, 0

    tokens_saved = 0
    result = []

    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            new_content = []
            changed = False
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and block.get("tool_use_id") in clear_ids
                    and block.get("content") != CLEARED_MESSAGE
                ):
                    old_content = block.get("content", "")
                    if isinstance(old_content, str):
                        tokens_saved += rough_token_count(old_content)
                    elif isinstance(old_content, list):
                        for sub in old_content:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                tokens_saved += rough_token_count(sub.get("text", ""))
                            elif isinstance(sub, dict) and sub.get("type") in ("image", "document"):
                                tokens_saved += 2000
                    new_block = copy.copy(block)
                    new_block["content"] = CLEARED_MESSAGE
                    new_content.append(new_block)
                    changed = True
                else:
                    new_content.append(block)
            if changed:
                new_msg = dict(msg)
                new_msg["content"] = new_content
                result.append(new_msg)
            else:
                result.append(msg)
        else:
            result.append(msg)

    return result, tokens_saved
