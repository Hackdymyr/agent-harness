"""Context compaction — LLM-based conversation summarization and cleanup.

Mirrors Claude Code's src/services/compact/ module. Provides:
- Token estimation (rough heuristic, no tokenizer dependency)
- Micro compaction (clear old tool results without LLM)
- Full compaction (LLM-generated conversation summaries)
- Auto compaction (trigger-based with circuit breaker)
"""

from agent_harness.compact.auto_compact import (
    AutoCompactState,
    auto_compact_if_needed,
    should_auto_compact,
)
from agent_harness.compact.compactor import (
    CompactConfig,
    CompactResult,
    compact_conversation,
    group_messages_by_round,
)
from agent_harness.compact.micro_compact import (
    CLEARED_MESSAGE,
    DEFAULT_COMPACTABLE_TOOLS,
    micro_compact,
)
from agent_harness.compact.prompt import (
    COMPACT_SYSTEM_PROMPT,
    format_compact_summary,
    get_compact_prompt,
)
from agent_harness.compact.token_estimation import (
    estimate_message_tokens,
    estimate_messages_tokens,
    rough_token_count,
)
