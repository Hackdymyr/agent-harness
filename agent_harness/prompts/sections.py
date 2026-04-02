"""Prompt sections — the building blocks of system prompts.

Mirrors Claude Code's systemPromptSections.ts pattern:
named, prioritized, conditionally included prompt fragments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable


class SectionPriority(IntEnum):
    """Priority levels for prompt sections. Lower values appear first."""

    OVERRIDE = 0   # Highest — identity overrides, critical constraints
    AGENT = 10     # Agent type role/identity
    CUSTOM = 20    # User-specified sections
    DEFAULT = 30   # Standard guidance (tool usage, style, safety)
    APPEND = 40    # Lowest — environment info, appended context


@dataclass
class PromptSection:
    """A named block of prompt text with priority and optional condition.

    Attributes:
        name: Unique identifier (e.g. "identity", "safety_policy").
        content: The prompt text.
        priority: Controls ordering in the assembled prompt.
        cacheable: Whether this content is stable across turns.
                   Metadata for LLM adapters that support prompt caching.
        condition: Optional predicate evaluated at build() time.
                   Receives a context dict. If it returns False, the section
                   is excluded from the final prompt.
    """

    name: str
    content: str
    priority: SectionPriority = SectionPriority.DEFAULT
    cacheable: bool = True
    condition: Callable[[dict[str, Any]], bool] | None = None
