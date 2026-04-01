"""agent_harness — A model-agnostic Python agent harness inspired by Claude Code's architecture.

Core concepts:
- AgentLoop: The tool-calling loop engine (messages → LLM → tools → results → loop)
- BaseTool / @tool: Define tools with Pydantic schemas
- ToolRegistry: Register, discover, and filter tools
- SubAgent: Spawn child agents with isolated context
- BaseLLM: Unified interface for any LLM provider

Quick start:
    from agent_harness import AgentLoop, AgentContext, AnthropicLLM, ToolRegistry, tool, ToolResult

    llm = AnthropicLLM(model="claude-sonnet-4-20250514")
    registry = ToolRegistry([my_tool_1, my_tool_2])
    ctx = AgentContext(messages=[], tools=registry, llm=llm)
    loop = AgentLoop(ctx)

    async for event in loop.run("Hello, do some work"):
        print(event.type, event)
"""

__version__ = "0.1.0"

# Core types
from agent_harness.types import (
    LLMResponse,
    Message,
    Role,
    StopReason,
    ToolCall,
    ToolDefinition,
    ToolResultContent,
    Usage,
)

# Agent
from agent_harness.agent.context import AgentContext
from agent_harness.agent.loop import AgentEvent, AgentLoop
from agent_harness.agent.sub_agent import SpawnAgentTool, SubAgent

# Tools
from agent_harness.tools.base import BaseTool, ToolRegistry, ToolResult, tool
from agent_harness.tools.orchestration import execute_tool_calls
from agent_harness.tools.permissions import PermissionChecker, PermissionMode, PermissionRule

# LLM Providers
from agent_harness.llm.base import BaseLLM
from agent_harness.llm.anthropic import AnthropicLLM
from agent_harness.llm.openai import OpenAILLM
from agent_harness.llm.openai_compat import OpenAICompatLLM

# Task Tracking
from agent_harness.tasks.tracker import Task, TaskStatus, TaskTracker

# Memory
from agent_harness.memory.store import FileMemoryStore, MemoryEntry

# LangGraph Integration
from agent_harness.integrations.langgraph import as_langgraph_node
