# agent_harness

<p align="center">
  <strong>A model-agnostic Python agent harness inspired by Claude Code's architecture</strong>
</p>

<p align="center">
  <a href="README.md">English</a> | <a href="README_zh.md">中文</a>
</p>

---

## Overview

`agent_harness` extracts core architectural patterns from Claude Code (Anthropic's official CLI tool, 500K+ lines of TypeScript) and reimplements them in ~2600 lines of Python as a lightweight, importable library. It focuses on filling the gap that frameworks like LangChain leave in the **single-agent execution layer** — tool-calling loops, concurrent orchestration, permission control, sub-agent isolation — while remaining compatible with any LLM provider.

## Key Features

| Feature | Description |
|---|---|
| **Agent Loop** | Core loop engine: messages -> LLM -> tool calls -> execute -> inject results -> loop. Inspired by Claude Code's `query.ts` |
| **Model-Agnostic** | Unified `BaseLLM` interface with built-in adapters for Anthropic / OpenAI / OpenAI-compatible endpoints (Ollama, vLLM, DeepSeek, Alibaba Cloud, etc.) |
| **Tool System** | Pydantic-based tool schemas, `@tool` decorator, ToolRegistry for registration/lookup/filtering |
| **Orchestration** | Read-only tools run concurrently, mutating tools run serially. Inspired by Claude Code's `toolOrchestration.ts` |
| **Permissions** | Three modes (auto_allow / ask_user / deny) + per-tool rule overrides |
| **Sub-Agent** | `context.fork()` creates isolated context (independent messages, tools, abort), runs AgentLoop recursively |
| **Prompt Engineering** | Section-based `SystemPromptBuilder` with priorities, agent type profiles, rich tool descriptions, environment detection |
| **Retry & Streaming** | Exponential backoff with error classification, real-time streaming via `chat_stream()` |
| **Context Compaction** | LLM-based conversation summarization, micro compaction (tool result cleanup), auto-trigger with circuit breaker |
| **Task Tracker** | In-memory task list with dependency tracking (blocks/blocked_by) |
| **Persistent Memory** | File-based persistent memory using Markdown + YAML frontmatter |
| **LangGraph Integration** | `as_langgraph_node()` turns an Agent into a LangGraph node in one line |

## Architecture

```
+--------------------------------+
|  LangGraph / Your orchestrator |  <- Coordination between agents
+--------------------------------+
|  agent_harness                 |  <- Single-agent tool loop engine
|  (this library)                |
|  +---------------------------+ |
|  | AgentLoop                 | |  Core loop
|  | ToolRegistry + @tool      | |  Tool registration
|  | PermissionChecker         | |  Permission control
|  | SubAgent (fork)           | |  Sub-agent isolation
|  | SystemPromptBuilder       | |  Prompt composition
|  | CompactConfig + auto      | |  Context compaction
|  | RetryConfig + streaming   | |  Retry & streaming
|  | TaskTracker               | |  Task tracking
|  | FileMemoryStore           | |  Persistent memory
|  +-----------+---------------+ |
|              |                 |
|  +-----------v---------------+ |
|  | BaseLLM abstraction       | |  Model-agnostic
|  |  +- AnthropicLLM          | |
|  |  +- OpenAILLM             | |
|  |  +- OpenAICompatLLM       | |  Ollama / vLLM / DeepSeek / ...
|  +---------------------------+ |
+--------------------------------+
```

## Installation

```bash
# Basic
pip install pydantic pyyaml

# Install for your LLM provider
pip install anthropic    # Claude
pip install openai       # OpenAI / OpenAI-compatible endpoints

# Or install from source
pip install -e ".[all]"
```

## Quick Start

### Basic Usage

```python
import asyncio
from pydantic import BaseModel, Field
from agent_harness import (
    AgentLoop, AgentContext, ToolRegistry, ToolResult, tool,
    OpenAICompatLLM,  # or AnthropicLLM, OpenAILLM
)

# 1. Choose your LLM
llm = OpenAICompatLLM(
    base_url="http://localhost:11434/v1",  # Ollama
    model="llama3",
)
# or:
# from agent_harness import AnthropicLLM
# llm = AnthropicLLM(model="claude-sonnet-4-20250514")

# 2. Define tools
class CalculateInput(BaseModel):
    expression: str = Field(description="Math expression")

@tool("calculate", "Evaluate a math expression", CalculateInput,
      is_read_only=True, is_concurrency_safe=True)
async def calculate(input: CalculateInput, ctx) -> ToolResult:
    result = eval(input.expression)  # Demo only
    return ToolResult(content=str(result))

# 3. Run the agent
async def main():
    ctx = AgentContext(
        messages=[],
        tools=ToolRegistry([calculate]),
        llm=llm,
        system_prompt="You are a math assistant. Use tools to calculate.",
    )
    loop = AgentLoop(ctx)

    async for event in loop.run("What is 42 * 37?"):
        if event.type == "tool_call":
            print(f"  Tool: {event.tool_call.name}({event.tool_call.input})")
        elif event.type == "tool_result":
            print(f"  Result: {event.tool_result.content}")
        elif event.type == "message" and event.message:
            print(f"  Assistant: {event.message.content}")

asyncio.run(main())
```

### Sub-Agent

```python
from agent_harness import SubAgent

sub = SubAgent(
    parent_context=ctx,
    prompt="Search for all TODO comments",
    tool_names={"grep", "read_file"},  # Only these tools
    system_prompt="You are a code search specialist",
    max_turns=20,
)
result = await sub.run_to_completion()
```

### Permission Control

```python
from agent_harness import PermissionChecker, PermissionMode, PermissionRule

checker = PermissionChecker(
    default_mode=PermissionMode.ASK_USER,
    ask_callback=my_confirm_fn,  # async (tool_name, desc, input) -> bool
    rules=[
        PermissionRule(tool_name="read_file", mode=PermissionMode.AUTO_ALLOW),
    ],
)
```

### Context Compaction

```python
from agent_harness import AgentLoop, AgentContext, CompactConfig

# Auto compaction is enabled by default
ctx = AgentContext(
    messages=[],
    tools=registry,
    llm=llm,
    context_window=200_000,  # Model's context window size
)

# Customize compaction behavior
compact_cfg = CompactConfig(
    context_window=200_000,
    buffer_tokens=13_000,       # Trigger compaction this many tokens before limit
    max_summary_tokens=20_000,  # Max tokens for the summary
    keep_recent_rounds=4,       # Keep the last N API rounds intact
)
loop = AgentLoop(ctx, compact_config=compact_cfg)

async for event in loop.run("Start working..."):
    if event.type == "compaction":
        print(f"Context compacted: {event.message.content}")
```

### LangGraph Multi-Agent

```python
from agent_harness import as_langgraph_node, AnthropicLLM
from langgraph.graph import StateGraph

coder = as_langgraph_node(
    llm=AnthropicLLM(model="claude-sonnet-4-20250514"),
    tools=[read_file, write_file, bash],
    system_prompt="You are an expert coder.",
)
reviewer = as_langgraph_node(
    llm=AnthropicLLM(model="claude-sonnet-4-20250514"),
    tools=[read_file],
    system_prompt="You are a code reviewer.",
)

graph = StateGraph(dict)
graph.add_node("coder", coder)
graph.add_node("reviewer", reviewer)
graph.add_edge("coder", "reviewer")
```

### Task Tracking

```python
from agent_harness import TaskTracker, TaskStatus

tracker = TaskTracker()
t1 = tracker.create("Implement auth", description="Add JWT")
t2 = tracker.create("Write tests", blocked_by=[t1.id])

tracker.update(t1.id, status=TaskStatus.COMPLETED)
print(tracker.available())  # [t2] — now unblocked
```

### Persistent Memory

```python
from agent_harness import FileMemoryStore

store = FileMemoryStore(".agent_memory")
store.write("user_pref", "Prefers concise answers", {"type": "feedback"})
results = store.search("concise")
```

## Project Structure

```
agent_harness/
+-- __init__.py                # Public API exports
+-- types.py                   # Shared types (Message, ToolCall, etc.)
+-- llm/
|   +-- base.py                # BaseLLM Protocol
|   +-- anthropic.py           # Claude adapter
|   +-- openai.py              # OpenAI adapter
|   +-- openai_compat.py       # Ollama / vLLM / DeepSeek / ...
|   +-- retry.py               # Exponential backoff + error classification
+-- tools/
|   +-- base.py                # BaseTool, @tool, ToolRegistry
|   +-- orchestration.py       # Concurrent/serial execution
|   +-- permissions.py         # Permission system
+-- agent/
|   +-- context.py             # AgentContext + fork()
|   +-- loop.py                # AgentLoop core loop engine
|   +-- sub_agent.py           # SubAgent + SpawnAgentTool
+-- compact/
|   +-- token_estimation.py    # Rough token counting (~4 chars/token)
|   +-- prompt.py              # 9-section summary template
|   +-- micro_compact.py       # Tool result cleanup (no LLM)
|   +-- compactor.py           # LLM-based conversation summarization
|   +-- auto_compact.py        # Auto-trigger with circuit breaker
+-- prompts/
|   +-- sections.py            # PromptSection + priorities
|   +-- builder.py             # SystemPromptBuilder
|   +-- agent_types.py         # Agent type profiles (general, explore)
|   +-- environment.py         # Runtime environment detection
|   +-- session.py             # Session-specific guidance
|   +-- tool_descriptions.py   # Rich per-tool descriptions
+-- memory/
|   +-- store.py               # FileMemoryStore
+-- tasks/
|   +-- tracker.py             # TaskTracker
+-- builtins/                  # 7 built-in tools
+-- integrations/
    +-- langgraph.py           # as_langgraph_node()
```

## Design Provenance

| Module | Inspired by (Claude Code) |
|---|---|
| `AgentLoop` | `query.ts` — queryLoop() |
| `BaseTool` / `@tool` | `Tool.ts` — Tool type + buildTool() |
| `ToolRegistry` | `tools.ts` — getAllBaseTools() + findToolByName() |
| `orchestration.py` | `toolOrchestration.ts` — partitionToolCalls() + runTools() |
| `PermissionChecker` | `permissions.ts` + `toolExecution.ts` |
| `AgentContext.fork()` | `subagentContext.ts` — createSubagentContext() |
| `SubAgent` | `AgentTool/runAgent.ts` |
| `compact/` | `services/compact/` — compactConversation() + autoCompact() |
| `prompts/` | `constants/prompts.ts` — system prompt assembly |
| `retry.py` | `services/api/` — retry with error classification |
| `TaskTracker` | TaskCreateTool / TaskUpdateTool / TaskListTool |
| `FileMemoryStore` | memdir/ + SessionMemory system |

## License

MIT
