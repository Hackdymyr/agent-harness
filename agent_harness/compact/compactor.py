"""Core compaction engine — LLM-based conversation summarization.

Mirrors Claude Code's compactConversation() from compact.ts.
Calls the LLM to summarize old messages, then replaces them with
the summary while preserving recent context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_harness.compact.prompt import (
    COMPACT_SYSTEM_PROMPT,
    format_compact_summary,
    get_compact_prompt,
)
from agent_harness.compact.token_estimation import estimate_messages_tokens
from agent_harness.llm.base import BaseLLM

logger = logging.getLogger(__name__)


@dataclass
class CompactConfig:
    """Configuration for conversation compaction.

    Mirrors Claude Code's compaction constants.
    """

    context_window: int = 200_000
    buffer_tokens: int = 13_000
    max_summary_tokens: int = 20_000
    max_consecutive_failures: int = 3
    keep_recent_rounds: int = 4
    custom_instructions: str | None = None


@dataclass
class CompactResult:
    """Result of a compaction operation."""

    messages: list[dict[str, Any]]
    summary_text: str = ""
    pre_compact_tokens: int = 0
    post_compact_tokens: int = 0
    was_compacted: bool = False


def group_messages_by_round(
    messages: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Group messages by API round (assistant response boundary).

    Each round starts with an assistant message and includes all subsequent
    tool result messages until the next assistant message.
    Mirrors Claude Code's groupMessagesByApiRound() from grouping.ts.
    """
    if not messages:
        return []

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for msg in messages:
        if msg.get("role") == "assistant" and current:
            groups.append(current)
            current = [msg]
        else:
            current.append(msg)

    if current:
        groups.append(current)

    return groups


async def compact_conversation(
    messages: list[dict[str, Any]],
    llm: BaseLLM,
    config: CompactConfig | None = None,
) -> CompactResult:
    """Compact a conversation by summarizing old messages with the LLM.

    Algorithm:
    1. Group messages by API round
    2. Split into "to summarize" (older) and "to keep" (recent)
    3. Call LLM to generate a summary of older messages
    4. Return: [summary_user_message] + kept_messages

    Args:
        messages: Full conversation message list.
        llm: LLM provider to generate the summary.
        config: Compaction configuration.

    Returns:
        CompactResult with the compacted messages.
    """
    if config is None:
        config = CompactConfig()

    pre_tokens = estimate_messages_tokens(messages)

    # Group by API round
    groups = group_messages_by_round(messages)

    if len(groups) <= config.keep_recent_rounds:
        # Not enough rounds to compact
        return CompactResult(
            messages=messages,
            pre_compact_tokens=pre_tokens,
            post_compact_tokens=pre_tokens,
            was_compacted=False,
        )

    # Split: summarize older groups, keep recent ones
    keep_count = config.keep_recent_rounds
    to_summarize_groups = groups[:-keep_count]
    to_keep_groups = groups[-keep_count:]

    messages_to_summarize = [m for g in to_summarize_groups for m in g]
    messages_to_keep = [m for g in to_keep_groups for m in g]

    # Build the summary request
    compact_prompt = get_compact_prompt(config.custom_instructions)

    # Call LLM with the old messages + summary request
    summary_messages = messages_to_summarize + [
        {"role": "user", "content": compact_prompt}
    ]

    try:
        response = await llm.chat(
            messages=summary_messages,
            system=COMPACT_SYSTEM_PROMPT,
            max_tokens=config.max_summary_tokens,
            temperature=0.0,
        )
        raw_summary = response.message.content
        if isinstance(raw_summary, list):
            raw_summary = " ".join(
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in raw_summary
            )
        summary_text = format_compact_summary(raw_summary)
    except Exception as e:
        logger.error(f"Compaction LLM call failed: {e}")
        return CompactResult(
            messages=messages,
            pre_compact_tokens=pre_tokens,
            post_compact_tokens=pre_tokens,
            was_compacted=False,
        )

    # Build compacted message list
    boundary_message: dict[str, Any] = {
        "role": "user",
        "content": (
            f"[This conversation was compacted. Below is a summary of the "
            f"conversation so far, followed by the most recent messages.]\n\n"
            f"{summary_text}"
        ),
    }

    compacted = [boundary_message] + messages_to_keep
    post_tokens = estimate_messages_tokens(compacted)

    logger.info(
        f"Compaction complete: {pre_tokens} -> {post_tokens} estimated tokens "
        f"({len(messages)} -> {len(compacted)} messages)"
    )

    return CompactResult(
        messages=compacted,
        summary_text=summary_text,
        pre_compact_tokens=pre_tokens,
        post_compact_tokens=post_tokens,
        was_compacted=True,
    )
