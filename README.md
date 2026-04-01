# agent_harness

**一个受 Claude Code 架构启发的、模型无关的 Python Agent 工具库**
**A model-agnostic Python agent harness library inspired by Claude Code's architecture**

---

## 简介 / Overview

`agent_harness` 从 Claude Code（Anthropic 官方 CLI 工具，50万+ 行 TypeScript）中提炼核心架构模式，用 ~1900 行 Python 重新实现为一个轻量级、可 import 的库。它专注于解决 LangChain 等框架在**单 Agent 执行层**的短板——工具调用循环、并发编排、权限控制、子 Agent 隔离——同时保持对任意 LLM 提供商的兼容性。

`agent_harness` extracts core architectural patterns from Claude Code (Anthropic's official CLI tool, 500K+ lines of TypeScript) and reimplements them in ~1900 lines of Python as a lightweight, importable library. It focuses on filling the gap that frameworks like LangChain leave in the **single-agent execution layer** — tool-calling loops, concurrent orchestration, permission control, sub-agent isolation — while remaining compatible with any LLM provider.

## 核心特性 / Key Features

| 特性 Feature | 说明 Description |
|---|---|
| **Agent Loop** | 核心循环引擎：消息 → LLM → 工具调用 → 执行 → 结果回注 → 循环。仿自 Claude Code 的 `query.ts` |
| | Core loop engine: messages → LLM → tool calls → execute → inject results → loop. Inspired by Claude Code's `query.ts` |
| **模型无关 Model-Agnostic** | 统一 `BaseLLM` 接口，内置 Anthropic / OpenAI / OpenAI 兼容（Ollama, vLLM, DeepSeek, 阿里云等）适配器 |
| | Unified `BaseLLM` interface with built-in adapters for Anthropic / OpenAI / OpenAI-compatible endpoints (Ollama, vLLM, DeepSeek, Alibaba Cloud, etc.) |
| **工具系统 Tool System** | Pydantic 定义工具 schema，`@tool` 装饰器，ToolRegistry 注册/查找/过滤 |
| | Pydantic-based tool schemas, `@tool` decorator, ToolRegistry for registration/lookup/filtering |
| **并发编排 Orchestration** | 只读工具自动并发执行，写入工具串行执行。仿自 Claude Code 的 `toolOrchestration.ts` |
| | Read-only tools run concurrently, mutating tools run serially. Inspired by Claude Code's `toolOrchestration.ts` |
| **权限系统 Permissions** | auto_allow / ask_user / deny 三模式 + 每工具规则覆盖 |
| | Three modes (auto_allow / ask_user / deny) + per-tool rule overrides |
| **子 Agent Sub-Agent** | `context.fork()` 创建隔离上下文（独立消息、工具、abort），递归运行 AgentLoop |
| | `context.fork()` creates isolated context (independent messages, tools, abort), runs AgentLoop recursively |
| **任务追踪 Task Tracker** | 内存任务列表 + 依赖关系（blocks/blocked_by） |
| | In-memory task list with dependency tracking (blocks/blocked_by) |
| **持久记忆 Memory** | 基于 Markdown + YAML frontmatter 的文件持久化记忆 |
| | File-based persistent memory using Markdown + YAML frontmatter |
| **LangGraph 集成** | `as_langgraph_node()` 一行代码将 Agent 变为 LangGraph 节点 |
| | `as_langgraph_node()` turns an Agent into a LangGraph node in one line |

## 架构 / Architecture

```
┌────────────────────────────────┐
│  LangGraph / 你的编排层         │  ← Agent 之间的协调、路由
│  LangGraph / Your orchestrator │  ← Coordination between agents
├────────────────────────────────┤
│  agent_harness                 │  ← 单 Agent 的工具循环引擎
│  (this library)                │  ← Single-agent tool loop engine
│  ┌──────────────────────────┐  │
│  │ AgentLoop                │  │  核心循环 / Core loop
│  │ ToolRegistry + @tool     │  │  工具注册 / Tool registration
│  │ PermissionChecker        │  │  权限控制 / Permission control
│  │ SubAgent (fork)          │  │  子Agent隔离 / Sub-agent isolation
│  │ TaskTracker              │  │  任务追踪 / Task tracking
│  │ FileMemoryStore          │  │  持久记忆 / Persistent memory
│  └──────────┬───────────────┘  │
│             │                  │
│  ┌──────────▼───────────────┐  │
│  │ BaseLLM 抽象层            │  │  模型无关接口 / Model-agnostic
│  │  ├ AnthropicLLM           │  │
│  │  ├ OpenAILLM              │  │
│  │  └ OpenAICompatLLM        │  │  Ollama / vLLM / DeepSeek / ...
│  └──────────────────────────┘  │
└────────────────────────────────┘
```

## 安装 / Installation

```bash
# 基本安装 / Basic
pip install pydantic pyyaml

# 根据你的 LLM 选择安装 / Install for your LLM provider
pip install anthropic    # Claude
pip install openai       # OpenAI / OpenAI-compatible endpoints

# 或直接从源码安装 / Or install from source
pip install -e ".[all]"
```

## 快速开始 / Quick Start

### 基本用法 / Basic Usage

```python
import asyncio
from pydantic import BaseModel, Field
from agent_harness import (
    AgentLoop, AgentContext, ToolRegistry, ToolResult, tool,
    OpenAICompatLLM,  # 或 AnthropicLLM, OpenAILLM
)

# 1. 选择 LLM / Choose your LLM
llm = OpenAICompatLLM(
    base_url="http://localhost:11434/v1",  # Ollama
    model="llama3",
)
# 或 / or:
# from agent_harness import AnthropicLLM
# llm = AnthropicLLM(model="claude-sonnet-4-20250514")

# 2. 定义工具 / Define tools
class CalculateInput(BaseModel):
    expression: str = Field(description="数学表达式 / Math expression")

@tool("calculate", "计算数学表达式 / Evaluate a math expression", CalculateInput,
      is_read_only=True, is_concurrency_safe=True)
async def calculate(input: CalculateInput, ctx) -> ToolResult:
    result = eval(input.expression)  # 仅示例 / Demo only
    return ToolResult(content=str(result))

# 3. 运行 Agent / Run the agent
async def main():
    ctx = AgentContext(
        messages=[],
        tools=ToolRegistry([calculate]),
        llm=llm,
        system_prompt="你是数学助手，请用工具计算。/ You are a math assistant, use tools to calculate.",
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

### 子 Agent / Sub-Agent

```python
from agent_harness import SubAgent

sub = SubAgent(
    parent_context=ctx,
    prompt="搜索所有 TODO 注释 / Search for all TODO comments",
    tool_names={"grep", "read_file"},  # 只给这些工具 / Only these tools
    system_prompt="你是代码搜索专家 / You are a code search specialist",
    max_turns=20,
)
result = await sub.run_to_completion()
```

### 权限控制 / Permission Control

```python
from agent_harness import PermissionChecker, PermissionMode, PermissionRule

# 写入操作需要确认 / Writing operations require confirmation
checker = PermissionChecker(
    default_mode=PermissionMode.ASK_USER,
    ask_callback=my_confirm_fn,  # async (tool_name, desc, input) -> bool
    rules=[
        PermissionRule(tool_name="read_file", mode=PermissionMode.AUTO_ALLOW),
    ],
)
```

### LangGraph 多 Agent / Multi-Agent with LangGraph

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

### 任务追踪 / Task Tracking

```python
from agent_harness import TaskTracker, TaskStatus

tracker = TaskTracker()
t1 = tracker.create("Implement auth", description="Add JWT")
t2 = tracker.create("Write tests", blocked_by=[t1.id])

tracker.update(t1.id, status=TaskStatus.COMPLETED)
print(tracker.available())  # [t2] — now unblocked
```

### 持久记忆 / Persistent Memory

```python
from agent_harness import FileMemoryStore

store = FileMemoryStore(".agent_memory")
store.write("user_pref", "Prefers concise answers", {"type": "feedback"})
results = store.search("concise")
```

## 项目结构 / Project Structure

```
agent_harness/
├── __init__.py                # 公共 API / Public API exports
├── types.py                   # 共享类型 / Shared types (Message, ToolCall, etc.)
├── llm/
│   ├── base.py                # BaseLLM Protocol
│   ├── anthropic.py           # Claude adapter
│   ├── openai.py              # OpenAI adapter
│   └── openai_compat.py       # Ollama / vLLM / DeepSeek / ...
├── tools/
│   ├── base.py                # BaseTool, @tool, ToolRegistry
│   ├── orchestration.py       # 并发/串行分区执行 / Concurrent/serial execution
│   └── permissions.py         # 权限系统 / Permission system
├── agent/
│   ├── context.py             # AgentContext + fork()
│   ├── loop.py                # AgentLoop 核心循环 / Core loop engine
│   └── sub_agent.py           # SubAgent + SpawnAgentTool
├── memory/
│   └── store.py               # FileMemoryStore
├── tasks/
│   └── tracker.py             # TaskTracker
└── integrations/
    └── langgraph.py           # as_langgraph_node()
```

## 设计来源 / Design Provenance

| 模块 Module | 灵感来源 Inspired by (Claude Code) |
|---|---|
| `AgentLoop` | `query.ts` — queryLoop() |
| `BaseTool` / `@tool` | `Tool.ts` — Tool type + buildTool() |
| `ToolRegistry` | `tools.ts` — getAllBaseTools() + findToolByName() |
| `orchestration.py` | `toolOrchestration.ts` — partitionToolCalls() + runTools() |
| `PermissionChecker` | `permissions.ts` + `toolExecution.ts` |
| `AgentContext.fork()` | `subagentContext.ts` — createSubagentContext() |
| `SubAgent` | `AgentTool/runAgent.ts` |
| `TaskTracker` | TaskCreateTool / TaskUpdateTool / TaskListTool |
| `FileMemoryStore` | memdir/ + SessionMemory system |

## 许可证 / License

MIT
