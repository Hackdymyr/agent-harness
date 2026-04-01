# 11 实战示例合集 / Practical Examples Cookbook

## 示例 1：文件操作 Agent / File Operation Agent

一个能读写文件和执行命令的完整 Agent：

```python
import asyncio
import subprocess
from pydantic import BaseModel, Field
from agent_harness import (
    AgentLoop, AgentContext, ToolRegistry, ToolResult, tool,
    PermissionChecker, PermissionMode,
    OpenAICompatLLM,
)

# ---- 工具定义 ----

class ReadFileInput(BaseModel):
    path: str = Field(description="文件路径")

@tool("read_file", "读取文件内容", ReadFileInput, is_read_only=True, is_concurrency_safe=True)
async def read_file(input: ReadFileInput, ctx) -> ToolResult:
    try:
        with open(input.path, encoding="utf-8") as f:
            return ToolResult(content=f.read())
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


class WriteFileInput(BaseModel):
    path: str = Field(description="文件路径")
    content: str = Field(description="要写入的内容")

@tool("write_file", "写入文件", WriteFileInput)
async def write_file(input: WriteFileInput, ctx) -> ToolResult:
    try:
        with open(input.path, "w", encoding="utf-8") as f:
            f.write(input.content)
        return ToolResult(content=f"已写入 {input.path}")
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


class BashInput(BaseModel):
    command: str = Field(description="Shell 命令")

@tool("bash", "执行 shell 命令", BashInput)
async def bash(input: BashInput, ctx) -> ToolResult:
    try:
        result = subprocess.run(
            input.command, shell=True, capture_output=True, text=True, timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        return ToolResult(content=output or "(无输出)", is_error=result.returncode != 0)
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


# ---- 运行 ----

async def main():
    llm = OpenAICompatLLM(base_url="...", model="...", api_key="...")

    ctx = AgentContext(
        messages=[],
        tools=ToolRegistry([read_file, write_file, bash]),
        llm=llm,
        permissions=PermissionChecker(
            default_mode=PermissionMode.ASK_USER,
            ask_callback=lambda name, desc, inp: __import__("asyncio").coroutine(
                lambda: input(f"允许 {name}? (y/n): ").lower() == "y"
            )(),
        ),
        system_prompt="你是一个文件操作助手。使用工具完成用户的请求。",
    )

    loop = AgentLoop(ctx)
    async for event in loop.run("帮我创建一个 hello.py，内容是 print('hello world')，然后运行它"):
        if event.type == "tool_call":
            print(f"  [工具] {event.tool_call.name}({event.tool_call.input})")
        elif event.type == "tool_result":
            print(f"  [结果] {event.tool_result.content[:100]}")
        elif event.type == "message" and event.message:
            print(f"  [助手] {event.message.content}")

asyncio.run(main())
```

---

## 示例 2：带记忆的 Agent / Agent with Memory

```python
from agent_harness import AgentLoop, AgentContext, ToolRegistry, ToolResult, tool, FileMemoryStore
from pydantic import BaseModel, Field

store = FileMemoryStore(".my_agent_memory")

# 启动时加载记忆
memories = store.list()
memory_context = ""
if memories:
    memory_context = "\n\n## 你的记忆:\n"
    for m in memories:
        memory_context += f"- [{m.metadata.get('type', '?')}] {m.name}: {m.content}\n"

# 定义记忆工具
class SaveMemoryInput(BaseModel):
    name: str = Field(description="记忆名称")
    content: str = Field(description="记忆内容")
    memory_type: str = Field(default="project", description="类型: user/feedback/project/reference")

@tool("save_memory", "保存一条记忆供将来使用", SaveMemoryInput)
async def save_memory(input: SaveMemoryInput, ctx) -> ToolResult:
    store.write(input.name, input.content, {
        "name": input.name,
        "type": input.memory_type,
    })
    return ToolResult(content=f"已保存记忆: {input.name}")

class RecallMemoryInput(BaseModel):
    query: str = Field(description="搜索关键词")

@tool("recall_memory", "搜索已保存的记忆", RecallMemoryInput, is_read_only=True, is_concurrency_safe=True)
async def recall_memory(input: RecallMemoryInput, ctx) -> ToolResult:
    results = store.search(input.query)
    if not results:
        return ToolResult(content="没有找到相关记忆")
    text = "\n".join(f"[{r.metadata.get('type', '?')}] {r.name}: {r.content}" for r in results)
    return ToolResult(content=text)

# 运行
ctx = AgentContext(
    messages=[],
    tools=ToolRegistry([save_memory, recall_memory, read_file]),  # + 其他工具
    llm=llm,
    system_prompt=f"你是一个聪明的助手，可以记住重要信息。{memory_context}",
)
```

---

## 示例 3：任务分解 Agent / Task Decomposition Agent

```python
from agent_harness import AgentLoop, AgentContext, ToolRegistry, ToolResult, tool, TaskTracker, TaskStatus
from pydantic import BaseModel, Field

tracker = TaskTracker()

# 暴露任务管理为工具
class CreateTaskInput(BaseModel):
    subject: str
    description: str = ""
    blocked_by: list[str] = Field(default_factory=list)

@tool("create_task", "创建一个任务", CreateTaskInput)
async def create_task(input: CreateTaskInput, ctx) -> ToolResult:
    t = tracker.create(input.subject, input.description, blocked_by=input.blocked_by)
    return ToolResult(content=f"创建任务: {t.id} - {t.subject}")

class UpdateTaskInput(BaseModel):
    task_id: str
    status: str = Field(description="pending / in_progress / completed")

@tool("update_task", "更新任务状态", UpdateTaskInput)
async def update_task(input: UpdateTaskInput, ctx) -> ToolResult:
    tracker.update(input.task_id, status=input.status)
    return ToolResult(content=f"任务 {input.task_id} 已更新为 {input.status}")

@tool("list_tasks", "列出所有任务", BaseModel, is_read_only=True, is_concurrency_safe=True)
async def list_tasks(input, ctx) -> ToolResult:
    tasks = tracker.list()
    if not tasks:
        return ToolResult(content="没有任务")
    lines = []
    for t in tasks:
        blocked = " (BLOCKED)" if tracker.is_blocked(t.id) else ""
        lines.append(f"[{t.status.value}] {t.id}: {t.subject}{blocked}")
    return ToolResult(content="\n".join(lines))

# Agent 会自主分解任务：
# "实现一个 REST API" → 自动 create_task × 5 → 逐个 update_task → 完成
```

---

## 示例 4：多 Agent 协作（无 LangGraph） / Multi-Agent without LangGraph

```python
async def coding_pipeline(requirement: str):
    """开发者 → 审查者 → 测试者 三阶段流水线"""

    # 阶段 1: 开发
    coder_ctx = AgentContext(
        messages=[], tools=ToolRegistry([read_file, write_file, bash]),
        llm=llm, system_prompt="你是 Python 开发者。根据需求编写代码。",
    )
    code_result = await AgentLoop(coder_ctx).run_to_completion(requirement)
    print(f"[开发者] {code_result.content[:200]}")

    # 阶段 2: 审查
    reviewer_ctx = AgentContext(
        messages=[], tools=ToolRegistry([read_file]),
        llm=llm, system_prompt="你是代码审查者。审查代码质量，指出问题。",
    )
    review_result = await AgentLoop(reviewer_ctx).run_to_completion(
        f"请审查开发者的工作:\n\n{code_result.content}"
    )
    print(f"[审查者] {review_result.content[:200]}")

    # 阶段 3: 测试
    tester_ctx = AgentContext(
        messages=[], tools=ToolRegistry([read_file, bash]),
        llm=llm, system_prompt="你是测试工程师。运行测试确保代码正确。",
    )
    test_result = await AgentLoop(tester_ctx).run_to_completion(
        f"开发者的代码已经过审查。请测试:\n\n审查结果: {review_result.content}"
    )
    print(f"[测试者] {test_result.content[:200]}")

    return test_result.content

# 运行
asyncio.run(coding_pipeline("实现一个计算斐波那契数列的函数，保存到 fib.py"))
```

---

## 示例 5：切换不同模型 / Switching Between Models

```python
from agent_harness import AnthropicLLM, OpenAILLM, OpenAICompatLLM

# 同一套工具和逻辑，不同模型
tools = ToolRegistry([read_file, write_file, bash])

# Claude
claude_ctx = AgentContext(messages=[], tools=tools,
    llm=AnthropicLLM(model="claude-sonnet-4-20250514"))

# GPT-4o
gpt_ctx = AgentContext(messages=[], tools=tools,
    llm=OpenAILLM(model="gpt-4o"))

# 本地 Ollama
local_ctx = AgentContext(messages=[], tools=tools,
    llm=OpenAICompatLLM(base_url="http://localhost:11434/v1", model="llama3"))

# 阿里云通义
qwen_ctx = AgentContext(messages=[], tools=tools,
    llm=OpenAICompatLLM(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus", api_key="sk-..."))

# 所有 ctx 用法完全一致
result = await AgentLoop(claude_ctx).run_to_completion("分析这个文件")
result = await AgentLoop(gpt_ctx).run_to_completion("分析这个文件")
result = await AgentLoop(local_ctx).run_to_completion("分析这个文件")
result = await AgentLoop(qwen_ctx).run_to_completion("分析这个文件")
```

这就是模型无关架构的价值——**换模型不改代码**。
