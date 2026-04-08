"""AgentContext — shared mutable state for an agent conversation.

Mirrors Claude Code's ToolUseContext, but without UI/React/IDE coupling.
The key feature is fork() for sub-agent isolation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from agent_harness.llm.base import BaseLLM
from agent_harness.tools.base import ToolRegistry
from agent_harness.tools.permissions import PermissionChecker, PermissionMode

if TYPE_CHECKING:
    from agent_harness.prompts.builder import SystemPromptBuilder


@dataclass
class AgentContext:
    """Shared state for a single agent conversation.

    Holds messages, tools, LLM client, permissions, and extensible metadata.
    Sub-agents receive an isolated copy via fork().

    system_prompt accepts either a plain string or a SystemPromptBuilder
    for rich, section-based prompt composition. Use resolve_system_prompt()
    to get the final string.
    """

    messages: list[dict[str, Any]]
    tools: ToolRegistry
    llm: BaseLLM
    permissions: PermissionChecker = field(
        default_factory=lambda: PermissionChecker(default_mode=PermissionMode.AUTO_ALLOW)
    )
    system_prompt: str | SystemPromptBuilder | None = None
    max_tokens: int = 4096
    max_turns: int = 100
    temperature: float = 0.0
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)

    # Identity
    agent_id: str = field(default_factory=lambda: f"agent_{uuid4().hex[:8]}")
    parent_context: AgentContext | None = None

    # Context window size (used by auto compaction to decide thresholds)
    context_window: int = 200_000

    # Extensible metadata (replaces Claude Code's AppState)
    metadata: dict[str, Any] = field(default_factory=dict)

    def fork(
        self,
        tools: ToolRegistry | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        max_tokens: int | None = None,
    ) -> AgentContext:
        """Create an isolated child context for sub-agent spawning.

        Mirrors createSubagentContext() from Claude Code:
        - Fresh message history
        - Optionally filtered tools
        - Independent abort signal
        - Shared LLM client and permission checker
        - Isolated metadata
        """
        return AgentContext(
            messages=[],  # Fresh conversation
            tools=tools if tools is not None else self.tools,
            llm=self.llm,
            permissions=self.permissions,
            system_prompt=system_prompt if system_prompt is not None else self.system_prompt,
            max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
            max_turns=max_turns if max_turns is not None else self.max_turns,
            temperature=self.temperature,
            context_window=self.context_window,
            abort_event=asyncio.Event(),  # Independent abort
            agent_id=f"agent_{uuid4().hex[:8]}",
            parent_context=self,
            metadata={},  # Isolated metadata
        )

    def abort(self) -> None:
        """Signal this agent to stop."""
        self.abort_event.set()

    def resolve_system_prompt(self) -> str | None:
        """Resolve system_prompt to a plain string for LLM calls.

        If system_prompt is a SystemPromptBuilder, calls build().
        If it's a string or None, returns as-is.
        """
        if self.system_prompt is None:
            return None
        if isinstance(self.system_prompt, str):
            return self.system_prompt
        # SystemPromptBuilder
        return self.system_prompt.build()

    @property
    def is_aborted(self) -> bool:
        return self.abort_event.is_set()
