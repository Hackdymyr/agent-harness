# 04 工具编排 / Tool Orchestration

## 概述 / Overview

当模型在一轮回复中请求调用多个工具时，工具编排器决定**如何执行它们**——哪些可以并发、哪些必须串行。

When the model requests multiple tool calls in one turn, the orchestrator decides **how to execute them** — which can run concurrently and which must run serially.

这个设计直接来源于 Claude Code 的 `toolOrchestration.ts`。

---

## 分区算法 / Partitioning Algorithm

核心函数 `partition_tool_calls()` 将一组工具调用分成若干**批次（batch）**：

```
输入: [tool_call_1, tool_call_2, tool_call_3, tool_call_4]

规则:
  - 连续的 read_only + concurrency_safe 工具 → 合并为一个并发批次
  - 其他工具 → 各自一个串行批次

输出:
  Batch 1 (concurrent): [tool_call_1, tool_call_2]  ← 两个都是只读
  Batch 2 (serial):     [tool_call_3]                ← 写入操作
  Batch 3 (concurrent): [tool_call_4]                ← 又一个只读（但单独因为前面是串行）
```

**执行流程**：
```
Batch 1: asyncio.gather(tool_call_1, tool_call_2)   ← 并发，快
         ↓ 等待全部完成
Batch 2: await tool_call_3                            ← 串行，一个一个来
         ↓ 等待完成
Batch 3: await tool_call_4                            ← 串行（只有一个所以无所谓）
```

---

## 为什么这样设计 / Why This Design

**场景 1：模型一次请求读 5 个文件**

```python
tool_calls = [
    read_file("a.py"),    # read_only=True, concurrency_safe=True
    read_file("b.py"),    # read_only=True, concurrency_safe=True
    read_file("c.py"),    # read_only=True, concurrency_safe=True
    read_file("d.py"),    # read_only=True, concurrency_safe=True
    read_file("e.py"),    # read_only=True, concurrency_safe=True
]

# 结果: 一个并发批次，5 个文件同时读
# 速度: 约等于读 1 个文件的时间（而不是 5 倍）
```

**场景 2：模型先读文件再写文件**

```python
tool_calls = [
    read_file("config.json"),   # read_only=True
    write_file("config.json"),  # read_only=False ← 必须在读之后
]

# 结果: 两个串行批次
# Batch 1: read_file  → 先执行
# Batch 2: write_file → 后执行
# 保证了执行顺序的正确性
```

**场景 3：混合操作**

```python
tool_calls = [
    grep("TODO"),               # read_only=True, concurrency_safe=True
    read_file("main.py"),       # read_only=True, concurrency_safe=True
    write_file("output.txt"),   # read_only=False
    read_file("result.txt"),    # read_only=True, concurrency_safe=True
]

# 结果:
# Batch 1 (concurrent): [grep, read_file]     ← 并发
# Batch 2 (serial):     [write_file]           ← 串行
# Batch 3 (serial):     [read_file]            ← 串行（因为在写之后，不能合并到 Batch 1）
```

---

## 并发限制 / Concurrency Limit

并发批次使用 `asyncio.Semaphore` 限制最大并发数，默认 **10**：

```python
results = await execute_tool_calls(
    tool_calls,
    registry,
    context,
    permission_checker,
    max_concurrency=10,  # 最多同时执行 10 个工具
)
```

---

## 单个工具的执行流程 / Single Tool Execution Flow

每个工具调用经过以下步骤：

```
1. 查找工具
   └─ registry.get(tool_call.name)
   └─ 找不到 → 返回错误 "Tool 'xxx' not found"

2. 验证输入
   └─ tool.validate_input(tool_call.input)  # Pydantic 校验
   └─ 无效 → 返回错误 "Input validation error: ..."

3. 权限检查（全局）
   └─ permission_checker.check(tool, input, context)
   └─ 拒绝 → 返回错误 "Permission denied"

4. 权限检查（工具级）
   └─ tool.check_permission(input, context)
   └─ 拒绝 → 返回错误 "Tool denied this operation"

5. 执行
   └─ tool.call(input, context) → ToolResult
   └─ 异常 → 返回错误 + traceback

6. 应用上下文更新
   └─ 如果 result.context_updates 不为空，更新 context.metadata

7. 包装结果
   └─ ToolResultContent(tool_use_id=..., content=..., is_error=...)
```

---

## 直接使用编排器 / Using the Orchestrator Directly

通常你不需要直接调用编排器（`AgentLoop` 会自动使用它），但如果你想自定义执行逻辑：

```python
from agent_harness import execute_tool_calls, ToolCall

results = await execute_tool_calls(
    tool_calls=[
        ToolCall(name="add", input={"a": 1, "b": 2}),
        ToolCall(name="multiply", input={"a": 3, "b": 4}),
    ],
    registry=my_registry,
    context=my_context,
    permission_checker=my_checker,
    max_concurrency=5,
)

for r in results:
    print(f"tool_use_id={r.tool_use_id}, content={r.content}, is_error={r.is_error}")
```
