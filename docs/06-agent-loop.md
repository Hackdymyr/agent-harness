# 06 Agent 循环 / Agent Loop

## 概述 / Overview

`AgentLoop` 是整个库的心脏——它驱动"消息 → LLM → 工具 → 结果 → 消息"的循环，直到模型完成任务。

`AgentLoop` is the heart of the library — it drives the "messages → LLM → tools → results → messages" cycle until the model completes the task.

---

## 最小示例 / Minimal Example

```python
import asyncio
from agent_harness import AgentLoop, AgentContext, ToolRegistry, OpenAICompatLLM

async def main():
    llm = OpenAICompatLLM(base_url="...", model="...", api_key="...")
    ctx = AgentContext(
        messages=[],
        tools=ToolRegistry([]),  # 无工具也能跑（纯对话）
        llm=llm,
    )
    loop = AgentLoop(ctx)

    async for event in loop.run("你好，请自我介绍"):
        if event.type == "message":
            print(event.message.content)

asyncio.run(main())
```

---

## AgentEvent 事件类型 / Event Types

`AgentLoop.run()` 是一个 AsyncGenerator，它 yield 以下事件：

| type | 含义 | 包含的数据 |
|------|------|-----------|
| `"message"` | 模型回复了一条消息 | `event.message` (Message), `event.usage` (token 用量) |
| `"tool_call"` | 模型请求调用工具 | `event.tool_call` (ToolCall) |
| `"tool_result"` | 工具执行完毕 | `event.tool_result` (ToolResultContent) |
| `"error"` | 出错了 | `event.error` (str) |
| `"done"` | 循环结束 | 无 |

**典型的事件序列**：

```
纯对话（无工具调用）:
  message → done

一次工具调用:
  message → tool_call → tool_result → message → done

多次工具调用:
  message → tool_call → tool_call → tool_result → tool_result → message → tool_call → tool_result → message → done
```

---

## 循环的完整逻辑 / Full Loop Logic

```
AgentLoop.run(user_input)
│
├─ 1. 追加用户消息到 context.messages
│
├─ 2. 循环开始 (最多 max_turns 轮)
│     │
│     ├─ 2a. 检查 abort 信号
│     │
│     ├─ 2b. 上下文管理（截断过长的消息历史）
│     │
│     ├─ 2c. 调用 LLM
│     │     llm.chat(
│     │       messages=context.messages,
│     │       tools=context.tools.definitions(),
│     │       system=context.system_prompt,
│     │     )
│     │
│     ├─ 2d. 追加助手消息到 context.messages
│     │
│     ├─ 2e. yield AgentEvent(type="message")
│     │
│     ├─ 2f. 检查是否有 tool_calls
│     │     │
│     │     ├─ 有 → 执行工具:
│     │     │     ├─ yield AgentEvent(type="tool_call") × N
│     │     │     ├─ execute_tool_calls(...)  ← 编排器处理并发/串行
│     │     │     ├─ 追加工具结果到 context.messages
│     │     │     ├─ yield AgentEvent(type="tool_result") × N
│     │     │     └─ continue → 回到 2a（下一轮 LLM 调用）
│     │     │
│     │     └─ 没有 → 检查 stop_reason:
│     │           ├─ MAX_TOKENS 且重试 < 3 → 注入"继续"消息, continue
│     │           └─ 其他 → yield AgentEvent(type="done"), return
│     │
│     └─ 超过 max_turns → yield error
│
└─ 结束
```

---

## AgentContext 参数详解 / AgentContext Parameters

```python
ctx = AgentContext(
    messages=[],               # 初始消息历史（通常为空）
    tools=registry,            # 工具注册表
    llm=llm,                   # LLM 客户端
    permissions=checker,       # 权限检查器（默认 AUTO_ALLOW）
    system_prompt="你是...",    # 系统提示（可选）
    max_tokens=4096,           # LLM 单次最大输出 token
    max_turns=100,             # 最大循环轮数（防止无限循环）
    temperature=0.0,           # 温度
    metadata={},               # 自定义元数据（工具可读写）
)
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `messages` | 必填 | 消息历史，通常传空列表 `[]` |
| `tools` | 必填 | ToolRegistry 实例 |
| `llm` | 必填 | BaseLLM 实例 |
| `permissions` | AUTO_ALLOW | PermissionChecker 实例 |
| `system_prompt` | None | 系统提示，定义 Agent 的角色/行为 |
| `max_tokens` | 4096 | LLM 单次最大输出 token 数 |
| `max_turns` | 100 | 最大循环轮数，避免 Agent 无限运行 |
| `temperature` | 0.0 | LLM 温度，0=确定性，1=创造性 |
| `metadata` | {} | 共享字典，工具可通过 context_updates 修改 |

---

## AgentLoop 参数 / AgentLoop Parameters

```python
loop = AgentLoop(
    context=ctx,
    on_tool_start=lambda tc: print(f"开始: {tc.name}"),   # 工具开始时回调
    on_tool_end=lambda tc, r: print(f"结束: {tc.name}"),   # 工具结束时回调
    max_context_messages=50,   # 上下文窗口：保留最近 50 条消息
)
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `context` | 必填 | AgentContext 实例 |
| `on_tool_start` | None | 每次工具开始执行时的回调 |
| `on_tool_end` | None | 每次工具执行完成时的回调 |
| `max_context_messages` | None | 不设置=不截断；设置后只保留最近 N 条消息 |

---

## 便捷方法 / Convenience Methods

### `run_to_completion()`

如果你不需要逐事件处理，只想拿到最终回复：

```python
result = await loop.run_to_completion("帮我计算 1+1")
print(result.content)  # "1+1=2"
```

返回最后一条助手消息（`Message` 对象），或 `None`（如果出错）。

---

## max_tokens 恢复机制 / Max Tokens Recovery

当模型的输出被 token 限制截断时（`stop_reason == MAX_TOKENS`），循环会自动注入一条消息要求模型继续：

```
LLM: "这段代码的问题在于第一，变量命名不规范；第二，缺少错误处理；第三——"
     stop_reason: MAX_TOKENS  ← 输出被截断

循环自动注入: "Your response was cut off due to token limits. Please continue from where you left off."

LLM: "第三，没有日志记录；第四，..."
     stop_reason: END_TURN  ← 这次说完了
```

最多重试 **3 次**，之后强制结束。

---

## 上下文窗口管理 / Context Window Management

当消息历史变得很长时，可以设置 `max_context_messages` 自动截断：

```python
loop = AgentLoop(ctx, max_context_messages=30)
```

**策略**：保留第一条消息（通常是初始用户请求）+ 最近 29 条消息。

```
消息历史: [msg_0, msg_1, msg_2, ..., msg_50]

截断后发给 LLM: [msg_0, msg_22, msg_23, ..., msg_50]
                  ↑ 保留第一条     ↑ 保留最近 29 条
```

**注意**：截断只影响发给 LLM 的消息，不影响 `context.messages` 中的完整历史。

---

## 中断 Agent / Aborting the Agent

```python
# 从外部中断正在运行的 Agent
ctx.abort()

# 循环会在下一轮开始时检测到 abort 信号，yield error 并停止
```

abort 信号是通过 `asyncio.Event` 实现的，线程安全。
