"""AgentContext — shared mutable state for an agent conversation.

Mirrors Claude Code's ToolUseContext, but without UI/React/IDE coupling.
The key feature is fork() for sub-agent isolation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from agent_harness.llm.base import BaseLLM
from agent_harness.tools.base import ToolRegistry
from agent_harness.tools.permissions import PermissionChecker, PermissionMode


@dataclass
class AgentContext:
    """Shared state for a single agent conversation.

    Holds messages, tools, LLM client, permissions, and extensible metadata.
    Sub-agents receive an isolated copy via fork().
    """

    messages: list[dict[str, Any]]
    tools: ToolRegistry
    llm: BaseLLM
    permissions: PermissionChecker = field(
        default_factory=lambda: PermissionChecker(default_mode=PermissionMode.AUTO_ALLOW)
    )
    system_prompt: str | None = None
    max_tokens: int = 4096
    max_turns: int = 100
    temperature: float = 0.0
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)

    # Identity
    agent_id: str = field(default_factory=lambda: f"agent_{uuid4().hex[:8]}")
    parent_context: AgentContext | None = None

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
            abort_event=asyncio.Event(),  # Independent abort
            agent_id=f"agent_{uuid4().hex[:8]}",
            parent_context=self,
            metadata={},  # Isolated metadata
        )

    def abort(self) -> None:
        """Signal this agent to stop."""
        self.abort_event.set()

    @property
    def is_aborted(self) -> bool:
        return self.abort_event.is_set()
