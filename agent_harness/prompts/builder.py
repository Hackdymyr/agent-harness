"""SystemPromptBuilder — section-based prompt composition engine.

Mirrors Claude Code's getSystemPrompt() + buildEffectiveSystemPrompt() pattern:
named sections with priorities, conditional inclusion, and layered assembly.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from agent_harness.prompts.sections import PromptSection, SectionPriority

if TYPE_CHECKING:
    from agent_harness.prompts.agent_types import AgentType


class SystemPromptBuilder:
    """Compose system prompts from named, prioritized sections.

    Sections are stored in insertion order and assembled by priority at
    build() time. Same-priority sections preserve insertion order.

    Usage:
        builder = SystemPromptBuilder()
        builder.add_section(PromptSection(name="identity", content="You are...", priority=SectionPriority.AGENT))
        builder.add_section(PromptSection(name="safety", content="Do not..."))
        prompt = builder.build()

    Backward compatibility:
        builder = SystemPromptBuilder.from_string("You are a helpful assistant.")
        prompt = builder.build()  # Returns the original string
    """

    def __init__(self) -> None:
        self._sections: dict[str, PromptSection] = {}
        self._insertion_order: dict[str, int] = {}
        self._counter: int = 0

    def add_section(self, section: PromptSection) -> SystemPromptBuilder:
        """Insert or overwrite a section by name. Returns self for chaining."""
        if section.name not in self._insertion_order:
            self._insertion_order[section.name] = self._counter
            self._counter += 1
        self._sections[section.name] = section
        return self

    def remove_section(self, name: str) -> SystemPromptBuilder:
        """Remove a section by name. No-op if absent. Returns self."""
        self._sections.pop(name, None)
        self._insertion_order.pop(name, None)
        return self

    def replace_section(self, name: str, content: str) -> SystemPromptBuilder:
        """Update the content of an existing section. No-op if absent."""
        if name in self._sections:
            section = self._sections[name]
            self._sections[name] = PromptSection(
                name=section.name,
                content=content,
                priority=section.priority,
                cacheable=section.cacheable,
                condition=section.condition,
            )
        return self

    def has_section(self, name: str) -> bool:
        return name in self._sections

    def sections(self) -> list[PromptSection]:
        """Return all sections sorted by (priority, insertion_order)."""
        return sorted(
            self._sections.values(),
            key=lambda s: (s.priority, self._insertion_order.get(s.name, 0)),
        )

    def build(self, context: dict[str, Any] | None = None) -> str:
        """Assemble the final prompt string.

        1. Filter out sections whose condition returns False
        2. Sort by (priority, insertion_order)
        3. Join with double newlines
        """
        ctx = context or {}
        parts: list[str] = []
        for section in self.sections():
            if section.condition is not None and not section.condition(ctx):
                continue
            if section.content.strip():
                parts.append(section.content)
        return "\n\n".join(parts)

    # ── Class Methods ────────────────────────────────────────────

    @classmethod
    def from_string(cls, text: str) -> SystemPromptBuilder:
        """Wrap a plain string as a single CUSTOM-priority section.

        This is the backward-compatibility bridge: existing code that
        passes system_prompt="..." can be converted to a builder.
        """
        builder = cls()
        builder.add_section(PromptSection(
            name="user_prompt",
            content=text,
            priority=SectionPriority.CUSTOM,
        ))
        return builder

    @classmethod
    def for_agent_type(cls, agent_type: AgentType, **kwargs: Any) -> SystemPromptBuilder:
        """Create a pre-configured builder for a known agent type.

        Delegates to agent_types module to avoid circular imports.
        """
        from agent_harness.prompts.agent_types import build_prompt_for_type
        return build_prompt_for_type(agent_type, **kwargs)

    def __repr__(self) -> str:
        names = [s.name for s in self.sections()]
        return f"SystemPromptBuilder(sections={names})"
