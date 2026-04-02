"""Sub-agent spawning — mirrors Claude Code's runAgent.ts + AgentTool.

Pattern: parent agent creates a child with isolated context (fresh messages,
filtered tools, separate abort), runs the same AgentLoop recursively,
and injects the result back into the parent conversation.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, TYPE_CHECKING

from pydantic import BaseModel, Field

from agent_harness.agent.context import AgentContext
from agent_harness.agent.loop import AgentEvent, AgentLoop
from agent_harness.tools.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from agent_harness.prompts.agent_types import AgentType


class SubAgent:
    """Spawn a child agent with isolated context.

    Usage:
        sub = SubAgent(
            parent_context=ctx,
            prompt="Search for all TODO comments in the codebase",
            tool_names={"grep", "read_file"},  # Only these tools
            system_prompt="You are a code search specialist.",
            max_turns=20,
        )
        result = await sub.run_to_completion()

    With agent type:
        from agent_harness.prompts import AgentType
        sub = SubAgent(
            parent_context=ctx,
            prompt="Explore the authentication module",
            agent_type=AgentType.EXPLORE,
            tool_names={"read_file", "grep", "glob", "list_dir"},
        )
    """

    def __init__(
        self,
        parent_context: AgentContext,
        prompt: str,
        system_prompt: str | None = None,
        agent_type: AgentType | None = None,
        tool_names: set[str] | None = None,
        exclude_tool_names: set[str] | None = None,
        max_turns: int = 30,
        max_tokens: int | None = None,
    ):
        # Resolve system prompt: agent_type takes precedence as base,
        # then system_prompt can override or be used standalone.
        resolved_prompt: str | Any = system_prompt
        if agent_type is not None:
            from agent_harness.prompts.builder import SystemPromptBuilder
            builder = SystemPromptBuilder.for_agent_type(agent_type)
            if system_prompt:
                # Append user's custom prompt to the agent type profile
                from agent_harness.prompts.sections import PromptSection, SectionPriority
                builder.add_section(PromptSection(
                    name="custom_instructions",
                    content=system_prompt,
                    priority=SectionPriority.CUSTOM,
                ))
            resolved_prompt = builder

        # Filter tools for the child
        filtered_tools = parent_context.tools.filter(
            names=tool_names,
            exclude=exclude_tool_names,
        )

        self.child_context = parent_context.fork(
            tools=filtered_tools,
            system_prompt=resolved_prompt,
            max_turns=max_turns,
            max_tokens=max_tokens,
        )
        self.prompt = prompt
        self.loop = AgentLoop(self.child_context)

    async def run(self) -> AsyncGenerator[AgentEvent, None]:
        """Run the sub-agent loop, yielding events."""
        async for event in self.loop.run(self.prompt):
            yield event

    async def run_to_completion(self) -> str:
        """Run sub-agent and return final text response."""
        result = await self.loop.run_to_completion(self.prompt)
        if result is None:
            return ""
        content = result.content
        if isinstance(content, str):
            return content
        return str(content)


# ----- Built-in spawn_agent tool -----
# This tool can be registered in any agent's ToolRegistry so the LLM
# can autonomously spawn sub-agents (like Claude Code's AgentTool).


class SpawnAgentInput(BaseModel):
    prompt: str = Field(description="The task for the sub-agent to perform")
    system_prompt: str | None = Field(
        default=None,
        description="Optional system prompt for the sub-agent",
    )
    allowed_tools: list[str] | None = Field(
        default=None,
        description="Tool names the sub-agent can use. None = inherit all.",
    )
    max_turns: int = Field(
        default=30,
        description="Maximum turns for the sub-agent",
    )


class SpawnAgentTool(BaseTool):
    """Built-in tool that lets the LLM spawn sub-agents."""

    name = "spawn_agent"
    description = (
        "Spawn a sub-agent to handle a subtask autonomously. "
        "The sub-agent runs with its own conversation context and "
        "returns its final response. Use this for parallel or specialized work."
    )
    input_model = SpawnAgentInput
    is_read_only = True  # The tool itself doesn't mutate — the sub-agent might
    is_concurrency_safe = True

    async def call(self, input: dict[str, Any], context: AgentContext) -> ToolResult:
        parsed = SpawnAgentInput.model_validate(input)

        sub = SubAgent(
            parent_context=context,
            prompt=parsed.prompt,
            system_prompt=parsed.system_prompt,
            tool_names=set(parsed.allowed_tools) if parsed.allowed_tools else None,
            max_turns=parsed.max_turns,
        )

        result = await sub.run_to_completion()
        return ToolResult(content=result if result else "(Sub-agent returned no output)")
