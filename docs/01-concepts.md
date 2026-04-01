# 01 核心概念与架构总览 / Core Concepts & Architecture

## 这个库是什么 / What is this library

`agent_harness` 是一个 **单 Agent 执行引擎**。它不负责多个 Agent 之间的协调（那是 LangGraph 的工作），而是负责一个 Agent 内部的核心能力：

- 接收用户指令
- 调用 LLM（任意模型）
- 解析模型返回的工具调用请求
- 执行工具
- 将结果反馈给模型
- 循环直到模型说"我完成了"

`agent_harness` is a **single-agent execution engine**. It doesn't coordinate between multiple agents (that's LangGraph's job). Instead, it handles one agent's core capabilities: receive instructions → call LLM → parse tool calls → execute tools → feed results back → loop until done.

---

## 层级关系 / Layer Relationship

```
你的应用 / Your Application
        │
        ▼
┌──────────────────────────────────┐
│  编排层 Orchestration Layer       │  LangGraph / 自定义 / Custom
│  (可选 Optional)                  │  管理多个 Agent 的协调
│                                   │  Manages coordination between agents
├──────────────────────────────────┤
│  agent_harness                    │  ← 本库 / This library
│  单 Agent 执行引擎                 │  ← Single-agent execution engine
│                                   │
│  AgentLoop ←→ ToolRegistry        │
│       ↕            ↕              │
│  AgentContext    BaseTool          │
│       ↕                           │
│  BaseLLM (任意模型)                │
├──────────────────────────────────┤
│  LLM SDK                          │  anthropic / openai / httpx
│  (底层 HTTP 调用)                  │  (Low-level HTTP calls)
└──────────────────────────────────┘
```

---

## 六个核心组件 / Six Core Components

### 1. BaseLLM — 模型抽象

**作用**：统一不同 LLM 提供商的调用接口。

你不需要关心 Anthropic 和 OpenAI 的 API 格式差异。`BaseLLM` 提供统一的 `chat()` 方法，接受统一的 `Message` 格式，返回统一的 `LLMResponse`。

**Purpose**: Unify the calling interface across different LLM providers. You don't need to worry about API format differences between Anthropic and OpenAI.

```
你的代码 → chat(messages, tools) → 统一的 LLMResponse
                    ↓
            AnthropicLLM  或  OpenAILLM  或  OpenAICompatLLM
                    ↓
            各自的 SDK 调用
```

### 2. BaseTool / @tool — 工具定义

**作用**：定义 Agent 可以使用的工具（函数）。

每个工具包含：
- **name**：工具名称（模型用这个名字来调用）
- **description**：描述（帮助模型理解什么时候该用这个工具）
- **input_model**：Pydantic 模型（定义参数格式，自动生成 JSON Schema）
- **call()**：实际执行逻辑
- **is_read_only / is_concurrency_safe**：行为标记（影响执行策略）

**Purpose**: Define tools (functions) the agent can use. Each tool has a name, description, Pydantic input model, execution logic, and behavior flags.

### 3. ToolRegistry — 工具注册表

**作用**：集中管理所有可用工具。

支持：注册、按名查找、过滤（给子 Agent 分配不同工具集）、批量转为 JSON Schema（发给 LLM）。

**Purpose**: Central management of all available tools. Supports: register, lookup by name, filter (for sub-agent tool scoping), bulk conversion to JSON Schema (for LLM API calls).

### 4. AgentContext — 会话上下文

**作用**：一次会话的全部状态。

包含：消息历史（messages）、工具注册表、LLM 客户端、权限检查器、系统提示、元数据。

关键方法 `fork()` 可以创建一个**隔离的子上下文**（消息清空、工具可过滤、abort 独立），用于生成子 Agent。

**Purpose**: All state for one conversation session. The key method `fork()` creates an isolated child context for sub-agent spawning.

### 5. AgentLoop — 核心循环引擎

**作用**：驱动整个 Agent 的行为循环。

循环逻辑：
```
用户消息 → LLM 调用 → 模型回复
    ↓
  有工具调用？ ──是──→ 执行工具 → 结果回注 → 回到 LLM 调用
    │
   否
    ↓
  输出最终回复，循环结束
```

这是一个 **AsyncGenerator**，通过 `async for event in loop.run(prompt)` 使用，每一步都会 yield 事件（消息、工具调用、工具结果、完成）。

**Purpose**: Drives the agent's behavior loop. It's an AsyncGenerator that yields events at each step.

### 6. PermissionChecker — 权限系统

**作用**：控制工具是否允许执行。

三种模式：
- `AUTO_ALLOW`：全部自动通过
- `ASK_USER`：只读工具自动通过，写入工具需要用户确认
- `DENY`：只允许只读工具

可以对单个工具设置特殊规则（覆盖全局模式）。

**Purpose**: Controls whether a tool is allowed to execute. Three modes + per-tool rule overrides.

---

## 数据流向图 / Data Flow

```
用户输入 "帮我读取 config.json"
    │
    ▼
AgentLoop.run("帮我读取 config.json")
    │
    ├─→ 追加到 context.messages: {role: "user", content: "帮我读取 config.json"}
    │
    ├─→ 调用 LLM:
    │     llm.chat(messages=[...], tools=[read_file, write_file, ...])
    │
    ├─→ LLM 返回:
    │     message: {role: "assistant", tool_calls: [{name: "read_file", input: {path: "config.json"}}]}
    │     stop_reason: "tool_use"
    │
    ├─→ yield AgentEvent(type="tool_call", ...)
    │
    ├─→ 工具编排:
    │     1. read_file 是只读+并发安全 → 并发批次
    │     2. 权限检查 → 通过
    │     3. 执行 read_file({"path": "config.json"}) → ToolResult(content="...")
    │
    ├─→ yield AgentEvent(type="tool_result", ...)
    │
    ├─→ 追加到 messages: {role: "user", content: [{tool_use_id: "...", content: "文件内容..."}]}
    │
    ├─→ 再次调用 LLM（带有工具结果的完整消息历史）
    │
    ├─→ LLM 返回:
    │     message: {role: "assistant", content: "config.json 的内容是..."}
    │     stop_reason: "end_turn"
    │
    ├─→ yield AgentEvent(type="message", ...)
    │
    └─→ yield AgentEvent(type="done")
```

---

## 与 Claude Code 的对应关系 / Mapping to Claude Code

如果你好奇本库的设计从何而来：

| 本库 This Library | Claude Code 源码 Source Code | 作用 Purpose |
|---|---|---|
| `AgentLoop` | `query.ts` 的 `queryLoop()` | 核心循环 |
| `AgentContext` | `ToolUseContext` | 会话状态容器 |
| `AgentContext.fork()` | `createSubagentContext()` | 子 Agent 隔离 |
| `BaseTool` | `Tool.ts` 的 `Tool` 类型 | 工具接口 |
| `@tool` 装饰器 | `buildTool()` 辅助函数 | 快捷定义工具 |
| `ToolRegistry` | `tools.ts` 的 `getAllBaseTools()` | 工具注册表 |
| `execute_tool_calls()` | `toolOrchestration.ts` 的 `runTools()` | 工具编排执行 |
| `PermissionChecker` | `permissions.ts` + `toolExecution.ts` | 权限系统 |
| `SubAgent` | `AgentTool` + `runAgent.ts` | 子 Agent 生成 |
| `BaseLLM` | 无（Claude Code 硬编码 Anthropic） | 模型抽象（新增） |
