"""Permission system — simplified from Claude Code's multi-layer hooks into auto/ask/deny."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Awaitable, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from agent_harness.tools.base import BaseTool
    from agent_harness.agent.context import AgentContext


class PermissionMode(str, Enum):
    AUTO_ALLOW = "auto_allow"       # All tools auto-approved
    ASK_USER = "ask_user"           # Non-read-only tools require confirmation
    DENY_NON_READONLY = "deny"      # Only read-only tools allowed


class PermissionRule(BaseModel):
    """Per-tool permission override."""

    tool_name: str
    mode: PermissionMode


class PermissionChecker:
    """Check whether a tool call is permitted.

    Modes:
    - AUTO_ALLOW: everything passes
    - ASK_USER: read-only tools pass; others call ask_callback (deny if no callback)
    - DENY: only read-only tools pass

    Per-tool rules override the default mode.
    """

    def __init__(
        self,
        default_mode: PermissionMode = PermissionMode.AUTO_ALLOW,
        rules: list[PermissionRule] | None = None,
        ask_callback: Callable[[str, str, dict[str, Any]], Awaitable[bool]] | None = None,
    ):
        """
        Args:
            default_mode: Global permission mode.
            rules: Per-tool overrides.
            ask_callback: Called when mode is ASK_USER for non-read-only tools.
                Signature: async (tool_name, description, input_dict) -> bool
                If None and mode is ASK_USER, defaults to deny.
        """
        self.default_mode = default_mode
        self._rules: dict[str, PermissionMode] = {}
        if rules:
            for r in rules:
                self._rules[r.tool_name] = r.mode
        self.ask_callback = ask_callback

    def _get_mode(self, tool_name: str) -> PermissionMode:
        return self._rules.get(tool_name, self.default_mode)

    async def check(
        self,
        tool: BaseTool,
        input: dict[str, Any],
        context: AgentContext,
    ) -> bool:
        """Returns True if tool execution is permitted."""
        mode = self._get_mode(tool.name)

        if mode == PermissionMode.AUTO_ALLOW:
            return True

        if mode == PermissionMode.DENY_NON_READONLY:
            return tool.is_read_only

        # ASK_USER mode
        if tool.is_read_only:
            return True

        if self.ask_callback:
            return await self.ask_callback(tool.name, tool.description, input)

        # No callback provided — deny by default
        return False
