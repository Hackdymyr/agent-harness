"""Session guidance — dynamic context sections for the current session.

Generates prompt sections based on available tools, memory state,
and detected environment. Mirrors the session_guidance section from
Claude Code's prompt system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_harness.prompts.sections import PromptSection, SectionPriority

if TYPE_CHECKING:
    from agent_harness.memory.store import MemoryEntry
    from agent_harness.prompts.agent_types import AgentType
    from agent_harness.tools.base import ToolRegistry


def generate_session_guidance(
    tools: "ToolRegistry",
    agent_type: "AgentType | None" = None,
    memory_entries: "list[MemoryEntry] | None" = None,
) -> list[PromptSection]:
    """Generate session-specific prompt sections.

    Args:
        tools: The ToolRegistry for this session (used to list available tools).
        agent_type: Optional agent type for type-specific guidance.
        memory_entries: Optional list of remembered context entries.

    Returns:
        List of PromptSection objects to add to a SystemPromptBuilder.
    """
    sections: list[PromptSection] = []

    # Tool inventory
    tool_names = sorted(tools.names()) if len(tools) > 0 else []
    if tool_names:
        tool_list = ", ".join(tool_names)
        sections.append(PromptSection(
            name="tool_inventory",
            content=f"# Available Tools\n\nYou have access to the following tools: {tool_list}.",
            priority=SectionPriority.DEFAULT,
            cacheable=False,
        ))

    # Memory context
    if memory_entries:
        memory_lines = ["# Remembered Context", ""]
        for entry in memory_entries:
            mem_type = entry.metadata.get("type", "general") if entry.metadata else "general"
            memory_lines.append(f"- [{mem_type}] **{entry.name}**: {entry.content[:200]}")
        sections.append(PromptSection(
            name="memory_context",
            content="\n".join(memory_lines),
            priority=SectionPriority.CUSTOM,
            cacheable=False,
        ))

    # Git guidance (conditional on bash tool being available)
    if "bash" in tools:
        sections.append(PromptSection(
            name="git_guidance",
            content="""\
# Git Safety Guidelines

When performing git operations:
- Prefer creating new commits over amending existing ones.
- Never force push to main/master without explicit user confirmation.
- Never skip hooks with --no-verify unless explicitly asked.
- Stage specific files by name rather than using git add -A or git add .
- Before destructive operations (reset --hard, checkout --, clean -f), confirm with the user.
- When a pre-commit hook fails, the commit did NOT happen — fix the issue and create a NEW commit.
- Include meaningful commit messages that describe the "why", not just the "what".""",
            priority=SectionPriority.DEFAULT,
        ))

    return sections
