# agent_harness

<p align="center">
  <strong>一个受 Claude Code 架构启发的、模型无关的 Python Agent 工具库</strong>
</p>

<p align="center">
  <a href="README.md">English</a> | <a href="README_zh.md">中文</a>
</p>

---

## 简介

`agent_harness` 从 Claude Code（Anthropic 官方 CLI 工具，50万+ 行 TypeScript）中提炼核心架构模式，用 ~2600 行 Python 重新实现为一个轻量级、可 import 的库。它专注于解决 LangChain 等框架在**单 Agent 执行层**的短板——工具调用循环、并发编排、权限控制、子 Agent 隔离——同时保持对任意 LLM 提供商的兼容性。

## 核心特性

| 特性 | 说明 |
|---|---|
| **Agent Loop** | 核心循环引擎：消息 -> LLM -> 工具调用 -> 执行 -> 结果回注 -> 循环。仿自 Claude Code 的 `query.ts` |
| **模型无关** | 统一 `BaseLLM` 接口，内置 Anthropic / OpenAI / OpenAI 兼容（Ollama, vLLM, DeepSeek, 阿里云等）适配器 |
| **工具系统** | Pydantic 定义工具 schema，`@tool` 装饰器，ToolRegistry 注册/查找/过滤 |
| **并发编排** | 只读工具自动并发执行，写入工具串行执行。仿自 Claude Code 的 `toolOrchestration.ts` |
| **权限系统** | auto_allow / ask_user / deny 三模式 + 每工具规则覆盖 |
| **子 Agent** | `context.fork()` 创建隔离上下文（独立消息、工具、abort），递归运行 AgentLoop |
| **提示词工程** | 分段式 `SystemPromptBuilder`，支持优先级、Agent 类型配置、富工具描述、环境检测 |
| **重试 & 流式** | 指数退避 + 错误分类重试引擎，`chat_stream()` 实时流式输出 |
| **上下文压缩** | LLM 摘要压缩、微压缩（工具结果清理）、自动触发 + 熔断器 |
| **任务追踪** | 内存任务列表 + 依赖关系（blocks/blocked_by） |
| **持久记忆** | 基于 Markdown + YAML frontmatter 的文件持久化记忆 |
| **LangGraph 集成** | `as_langgraph_node()` 一行代码将 Agent 变为 LangGraph 节点 |

## 架构

```
+--------------------------------+
|  LangGraph / 你的编排层         |  <- Agent 之间的协调、路由
+--------------------------------+
|  agent_harness                 |  <- 单 Agent 的工具循环引擎
|  (this library)                |
|  +---------------------------+ |
|  | AgentLoop                 | |  核心循环
|  | ToolRegistry + @tool      | |  工具注册
|  | PermissionChecker         | |  权限控制
|  | SubAgent (fork)           | |  子Agent隔离
|  | SystemPromptBuilder       | |  提示词组合
|  | CompactConfig + auto      | |  上下文压缩
|  | RetryConfig + streaming   | |  重试 & 流式
|  | TaskTracker               | |  任务追踪
|  | FileMemoryStore           | |  持久记忆
|  +-----------+---------------+ |
|              |                 |
|  +-----------v---------------+ |
|  | BaseLLM 抽象层             | |  模型无关接口
|  |  +- AnthropicLLM          | |
|  |  +- OpenAILLM             | |
|  |  +- OpenAICompatLLM       | |  Ollama / vLLM / DeepSeek / ...
|  +---------------------------+ |
+--------------------------------+
```

## 安装

```bash
# 基本安装
pip install pydantic pyyaml

# 根据你的 LLM 选择安装
pip install anthropic    # Claude
pip install openai       # OpenAI / OpenAI 兼容接口

# 或直接从源码安装
pip install -e ".[all]"
```

## 快速开始

### 基本用法

```python
import asyncio
from pydantic import BaseModel, Field
from agent_harness import (
    AgentLoop, AgentContext, ToolRegistry, ToolResult, tool,
    OpenAICompatLLM,  # 或 AnthropicLLM, OpenAILLM
)

# 1. 选择 LLM
llm = OpenAICompatLLM(
    base_url="http://localhost:11434/v1",  # Ollama
    model="llama3",
)
# 或:
# from agent_harness import AnthropicLLM
# llm = AnthropicLLM(model="claude-sonnet-4-20250514")

# 2. 定义工具
class CalculateInput(BaseModel):
    expression: str = Field(description="数学表达式")

@tool("calculate", "计算数学表达式", CalculateInput,
      is_read_only=True, is_concurrency_safe=True)
async def calculate(input: CalculateInput, ctx) -> ToolResult:
    result = eval(input.expression)  # 仅示例
    return ToolResult(content=str(result))

# 3. 运行 Agent
async def main():
    ctx = AgentContext(
        messages=[],
        tools=ToolRegistry([calculate]),
        llm=llm,
        system_prompt="你是数学助手，请用工具计算。",
    )
    loop = AgentLoop(ctx)

    async for event in loop.run("42 乘以 37 等于多少？"):
        if event.type == "tool_call":
            print(f"  工具: {event.tool_call.name}({event.tool_call.input})")
        elif event.type == "tool_result":
            print(f"  结果: {event.tool_result.content}")
        elif event.type == "message" and event.message:
            print(f"  助手: {event.message.content}")

asyncio.run(main())
```

### 子 Agent

```python
from agent_harness import SubAgent

sub = SubAgent(
    parent_context=ctx,
    prompt="搜索所有 TODO 注释",
    tool_names={"grep", "read_file"},  # 只给这些工具
    system_prompt="你是代码搜索专家",
    max_turns=20,
)
result = await sub.run_to_completion()
```

### 权限控制

```python
from agent_harness import PermissionChecker, PermissionMode, PermissionRule

# 写入操作需要确认
checker = PermissionChecker(
    default_mode=PermissionMode.ASK_USER,
    ask_callback=my_confirm_fn,  # async (tool_name, desc, input) -> bool
    rules=[
        PermissionRule(tool_name="read_file", mode=PermissionMode.AUTO_ALLOW),
    ],
)
```

### 上下文压缩

```python
from agent_harness import AgentLoop, AgentContext, CompactConfig

# 自动压缩默认开启
ctx = AgentContext(
    messages=[],
    tools=registry,
    llm=llm,
    context_window=200_000,  # 模型的上下文窗口大小
)

# 自定义压缩行为
compact_cfg = CompactConfig(
    context_window=200_000,
    buffer_tokens=13_000,       # 距离限制这么多 token 时触发压缩
    max_summary_tokens=20_000,  # 摘要最大 token 数
    keep_recent_rounds=4,       # 保留最近 N 轮 API 交互
)
loop = AgentLoop(ctx, compact_config=compact_cfg)

async for event in loop.run("开始工作..."):
    if event.type == "compaction":
        print(f"上下文已压缩: {event.message.content}")
```

### LangGraph 多 Agent

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

### 任务追踪

```python
from agent_harness import TaskTracker, TaskStatus

tracker = TaskTracker()
t1 = tracker.create("实现认证", description="添加 JWT")
t2 = tracker.create("编写测试", blocked_by=[t1.id])

tracker.update(t1.id, status=TaskStatus.COMPLETED)
print(tracker.available())  # [t2] — 现在可以开始了
```

### 持久记忆

```python
from agent_harness import FileMemoryStore

store = FileMemoryStore(".agent_memory")
store.write("user_pref", "偏好简洁回答", {"type": "feedback"})
results = store.search("简洁")
```

## 项目结构

```
agent_harness/
+-- __init__.py                # 公共 API 导出
+-- types.py                   # 共享类型 (Message, ToolCall, etc.)
+-- llm/
|   +-- base.py                # BaseLLM Protocol
|   +-- anthropic.py           # Claude 适配器
|   +-- openai.py              # OpenAI 适配器
|   +-- openai_compat.py       # Ollama / vLLM / DeepSeek / ...
|   +-- retry.py               # 指数退避 + 错误分类
+-- tools/
|   +-- base.py                # BaseTool, @tool, ToolRegistry
|   +-- orchestration.py       # 并发/串行分区执行
|   +-- permissions.py         # 权限系统
+-- agent/
|   +-- context.py             # AgentContext + fork()
|   +-- loop.py                # AgentLoop 核心循环引擎
|   +-- sub_agent.py           # SubAgent + SpawnAgentTool
+-- compact/
|   +-- token_estimation.py    # 粗估 Token 计数 (~4字符/token)
|   +-- prompt.py              # 9段摘要模板
|   +-- micro_compact.py       # 工具结果清理（无需 LLM）
|   +-- compactor.py           # LLM 摘要压缩引擎
|   +-- auto_compact.py        # 自动触发 + 熔断器
+-- prompts/
|   +-- sections.py            # PromptSection + 优先级
|   +-- builder.py             # SystemPromptBuilder
|   +-- agent_types.py         # Agent 类型配置 (general, explore)
|   +-- environment.py         # 运行环境检测
|   +-- session.py             # 会话级指导
|   +-- tool_descriptions.py   # 富工具描述
+-- memory/
|   +-- store.py               # FileMemoryStore
+-- tasks/
|   +-- tracker.py             # TaskTracker
+-- builtins/                  # 7 个内置工具
+-- integrations/
    +-- langgraph.py           # as_langgraph_node()
```

## 设计来源

| 模块 | 灵感来源 (Claude Code) |
|---|---|
| `AgentLoop` | `query.ts` — queryLoop() |
| `BaseTool` / `@tool` | `Tool.ts` — Tool type + buildTool() |
| `ToolRegistry` | `tools.ts` — getAllBaseTools() + findToolByName() |
| `orchestration.py` | `toolOrchestration.ts` — partitionToolCalls() + runTools() |
| `PermissionChecker` | `permissions.ts` + `toolExecution.ts` |
| `AgentContext.fork()` | `subagentContext.ts` — createSubagentContext() |
| `SubAgent` | `AgentTool/runAgent.ts` |
| `compact/` | `services/compact/` — compactConversation() + autoCompact() |
| `prompts/` | `constants/prompts.ts` — 系统提示词组装 |
| `retry.py` | `services/api/` — 错误分类重试 |
| `TaskTracker` | TaskCreateTool / TaskUpdateTool / TaskListTool |
| `FileMemoryStore` | memdir/ + SessionMemory system |

## 许可证

MIT
