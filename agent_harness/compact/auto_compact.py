"""Auto compaction — trigger compaction based on token thresholds.

Mirrors Claude Code's autoCompact.ts. Monitors token usage and
automatically triggers compaction when the context grows too large.
Includes a circuit breaker that stops after N consecutive failures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_harness.compact.compactor import CompactConfig, CompactResult, compact_conversation
from agent_harness.compact.micro_compact import micro_compact
from agent_harness.compact.token_estimation import estimate_messages_tokens
from agent_harness.llm.base import BaseLLM

logger = logging.getLogger(__name__)


@dataclass
class AutoCompactState:
    """Tracks auto compaction state across loop iterations.

    The circuit breaker stops compaction attempts after
    max_consecutive_failures to avoid burning tokens on
    repeated failures.
    """

    consecutive_failures: int = 0
    last_token_count: int = 0


def should_auto_compact(
    messages: list[dict[str, Any]],
    context_window: int,
    config: CompactConfig | None = None,
) -> bool:
    """Check if automatic compaction should be triggered.

    Mirrors Claude Code's shouldAutoCompact() — compares estimated
    token usage against (context_window - buffer_tokens - max_summary_tokens).

    Returns True when token usage exceeds the threshold.
    """
    if config is None:
        config = CompactConfig()

    effective_window = context_window - config.max_summary_tokens
    threshold = effective_window - config.buffer_tokens

    estimated = estimate_messages_tokens(messages)
    return estimated >= threshold


async def auto_compact_if_needed(
    messages: list[dict[str, Any]],
    llm: BaseLLM,
    config: CompactConfig | None = None,
    state: AutoCompactState | None = None,
) -> CompactResult | None:
    """Run auto compaction if the context exceeds the threshold.

    Steps:
    1. Check token threshold
    2. If exceeded, try micro compaction first
    3. If still exceeded, run full LLM compaction
    4. Track consecutive failures for circuit breaker

    Args:
        messages: Current conversation messages.
        llm: LLM provider for generating summaries.
        config: Compaction configuration.
        state: Mutable state for tracking failures across calls.

    Returns:
        CompactResult if compaction ran, None if not needed or circuit-broken.
    """
    if config is None:
        config = CompactConfig()
    if state is None:
        state = AutoCompactState()

    # Circuit breaker: stop after N consecutive failures
    if state.consecutive_failures >= config.max_consecutive_failures:
        logger.warning(
            f"Auto compaction circuit breaker tripped "
            f"({state.consecutive_failures} consecutive failures)"
        )
        return None

    # Check if compaction is needed
    if not should_auto_compact(messages, config.context_window, config):
        return None

    logger.info("Auto compaction triggered — context approaching limit")

    # Step 1: Try micro compaction first (lightweight, no LLM call)
    mc_messages, tokens_saved = micro_compact(messages)
    if tokens_saved > 0:
        logger.info(f"Micro compaction freed ~{tokens_saved} estimated tokens")
        # Re-check if micro compaction was enough
        if not should_auto_compact(mc_messages, config.context_window, config):
            state.consecutive_failures = 0
            return CompactResult(
                messages=mc_messages,
                pre_compact_tokens=estimate_messages_tokens(messages),
                post_compact_tokens=estimate_messages_tokens(mc_messages),
                was_compacted=True,
                summary_text="",
            )
        # Use micro-compacted messages as input to full compaction
        messages = mc_messages

    # Step 2: Full LLM compaction
    result = await compact_conversation(messages, llm, config)

    if result.was_compacted:
        state.consecutive_failures = 0
        logger.info(
            f"Full compaction: {result.pre_compact_tokens} -> "
            f"{result.post_compact_tokens} estimated tokens"
        )
    else:
        state.consecutive_failures += 1
        logger.warning(
            f"Compaction failed (consecutive failures: {state.consecutive_failures})"
        )

    return result
