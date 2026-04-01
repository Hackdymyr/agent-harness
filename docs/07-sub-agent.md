# 07 子 Agent / Sub-Agent

## 概述 / Overview

子 Agent 是在父 Agent 运行过程中**动态生成**的独立 Agent。它拥有隔离的上下文（独立消息历史、可过滤的工具集、独立的 abort 信号），执行完毕后将结果返回给父 Agent。

Sub-agents are independent agents **dynamically spawned** during a parent agent's run. They have isolated context (independent message history, filtered tools, separate abort signal) and return results to the parent when done.

---

## 核心原理 / Core Mechanism

```
父 Agent 运行中:

  用户: "帮我重构这个项目"
  ↓
  父 Agent (LLM): "我需要先了解项目结构，让我生成一个子 Agent 来搜索"
  ↓
  调用 spawn_agent 工具
  ↓
  ┌─────────────────────────────────────────┐
  │  子 Agent (隔离的上下文)                   │
  │                                          │
  │  messages: []  ← 全新的空消息历史          │
  │  tools: {grep, read_file}  ← 过滤后的     │
  │  llm: 同一个 LLM 客户端                   │
  │  abort: 独立的信号                         │
  │  system_prompt: "你是代码搜索专家"          │
  │                                          │
  │  运行自己的 AgentLoop...                   │
  │  → 调用 grep 搜索 TODO                    │
  │  → 调用 read_file 读取关键文件              │
  │  → 返回总结                                │
  └─────────────────────────────────────────┘
  ↓
  子 Agent 结果注入父 Agent 的消息历史
  ↓
  父 Agent 继续: "好的，根据搜索结果，我来开始重构..."
```

---

## 使用方式一：在代码中直接使用 / Direct Usage

```python
from agent_harness import SubAgent

sub = SubAgent(
    parent_context=ctx,                # 父 Agent 的上下文
    prompt="搜索所有 TODO 注释",          # 给子 Agent 的任务
    tool_names={"grep", "read_file"},   # 只给这些工具（None = 继承全部）
    system_prompt="你是代码搜索专家",      # 子 Agent 的系统提示（None = 继承父的）
    max_turns=20,                       # 子 Agent 的最大循环轮数
)

# 方式 A: 直接获取最终结果
result_text = await sub.run_to_completion()
print(result_text)

# 方式 B: 逐事件监听
async for event in sub.run():
    print(event.type, event)
```

### 参数详解 / Parameters

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `parent_context` | AgentContext | 是 | 父 Agent 的上下文 |
| `prompt` | str | 是 | 给子 Agent 的任务描述 |
| `tool_names` | set[str] | 否 | 子 Agent 可用的工具名集合。None = 继承父 Agent 的全部工具 |
| `exclude_tool_names` | set[str] | 否 | 要排除的工具名集合 |
| `system_prompt` | str | 否 | 子 Agent 的系统提示。None = 继承父 Agent 的 |
| `max_turns` | int | 否 | 最大循环轮数，默认 30 |
| `max_tokens` | int | 否 | None = 继承父 Agent 的 |

---

## 使用方式二：让 LLM 自主生成子 Agent / LLM-Driven Spawning

注册 `SpawnAgentTool`，模型可以自主决定何时生成子 Agent：

```python
from agent_harness import SpawnAgentTool, ToolRegistry

registry = ToolRegistry([
    read_file,
    write_file,
    grep,
    SpawnAgentTool(),  # ← 加上这个
])
```

模型会看到这个工具的描述，并在需要时自主调用：

```
模型: 我需要并行搜索两个方面的代码，让我生成一个子 Agent。
→ tool_call: spawn_agent({
    prompt: "搜索所有数据库相关的代码",
    allowed_tools: ["grep", "read_file"],
    max_turns: 15,
  })
→ 子 Agent 运行...
→ 结果返回给模型
```

---

## 上下文隔离详解 / Context Isolation

`SubAgent` 内部调用 `parent_context.fork()` 创建子上下文。隔离规则：

| 属性 | 父子关系 | 说明 |
|------|---------|------|
| `messages` | **隔离** | 子 Agent 从空列表开始 |
| `tools` | **可过滤** | 可以只给子 Agent 一部分工具 |
| `llm` | **共享** | 使用同一个 LLM 客户端（省资源） |
| `permissions` | **共享** | 同一套权限规则 |
| `abort_event` | **隔离** | 中断子 Agent 不影响父 Agent |
| `metadata` | **隔离** | 子 Agent 有自己的 metadata 字典 |
| `system_prompt` | **可覆盖** | 可以给子 Agent 不同的角色设定 |
| `parent_context` | **引用** | 子 Agent 持有父上下文的引用 |

**为什么 messages 要隔离？**
子 Agent 的任务通常很具体（"搜索 TODO"），不需要看到父 Agent 的完整对话历史。隔离后：
- 子 Agent 的上下文窗口更短，LLM 调用更快
- 减少干扰，子 Agent 更专注

**为什么 llm 要共享？**
创建新的 HTTP 客户端没有意义，复用连接池更高效。

---

## 嵌套子 Agent / Nested Sub-Agents

子 Agent 可以继续生成子 Agent（如果它的工具集中包含 SpawnAgentTool）：

```
父 Agent
  └─ 子 Agent A (搜索模块)
       └─ 子 Agent A1 (搜索 frontend)
       └─ 子 Agent A2 (搜索 backend)
  └─ 子 Agent B (重构模块)
```

**注意**：嵌套层数没有硬限制，但每一层都会消耗 token。建议通过 `max_turns` 控制深度。
