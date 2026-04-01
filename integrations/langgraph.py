"""LangGraph integration — thin adapter to use AgentLoop as a graph node.

Usage with LangGraph:

    from agent_harness import AnthropicLLM, ToolRegistry, as_langgraph_node
    from agent_harness.tools import BaseTool
    from langgraph.graph import StateGraph

    # Define your tools
    tools = [read_file_tool, bash_tool, grep_tool]

    # Create nodes
    coder = as_langgraph_node(
        llm=AnthropicLLM(model="claude-sonnet-4-20250514"),
        tools=tools,
        system_prompt="You are an expert Python developer.",
    )
    reviewer = as_langgraph_node(
        llm=AnthropicLLM(model="claude-sonnet-4-20250514"),
        tools=[read_file_tool],
        system_prompt="You are a code reviewer.",
    )

    # Build graph
    graph = StateGraph(dict)
    graph.add_node("coder", coder)
    graph.add_node("reviewer", reviewer)
    graph.add_edge("coder", "reviewer")
"""

from __future__ import annotations

from typing import Any, Callable

from agent_harness.agent.context import AgentContext
from agent_harness.agent.loop import AgentLoop
from agent_harness.llm.base import BaseLLM
from agent_harness.tools.base import BaseTool, ToolRegistry
from agent_harness.tools.permissions import PermissionChecker, PermissionMode
from agent_harness.types import Role


def as_langgraph_node(
    llm: BaseLLM,
    tools: list[BaseTool] | None = None,
    system_prompt: str | None = None,
    permission_mode: PermissionMode = PermissionMode.AUTO_ALLOW,
    max_turns: int = 50,
    max_tokens: int = 4096,
) -> Callable:
    """Create a LangGraph-compatible node from agent_harness.

    The returned async function has signature:
        async def node(state: dict) -> dict

    State contract:
        Input:
            - "messages": list[dict] — conversation history (optional)
            - "input": str — user prompt for this node (required)
        Output:
            - "messages": list[dict] — updated full conversation
            - "output": str — final assistant response text
    """

    async def node(state: dict[str, Any]) -> dict[str, Any]:
        registry = ToolRegistry(tools) if tools else ToolRegistry()
        permissions = PermissionChecker(default_mode=permission_mode)

        # Build messages from state
        existing_messages = [
            msg for msg in state.get("messages", [])
            if isinstance(msg, dict)
        ]

        context = AgentContext(
            messages=list(existing_messages),
            tools=registry,
            llm=llm,
            permissions=permissions,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            max_turns=max_turns,
        )

        loop = AgentLoop(context)
        user_input = state.get("input", "")

        if not user_input:
            return {
                "messages": existing_messages,
                "output": "",
            }

        result = await loop.run_to_completion(user_input)

        return {
            "messages": context.messages,
            "output": result.content if result else "",
        }

    return node
