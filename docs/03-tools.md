# 03 工具系统 / Tool System

## 概述 / Overview

工具（Tool）是 Agent 能力的载体。模型通过"调用工具"来与外部世界交互——读文件、执行命令、搜索代码、调用 API 等。

Tools are the carrier of an agent's capabilities. The model interacts with the outside world by "calling tools" — reading files, executing commands, searching code, calling APIs, etc.

---

## 定义工具的两种方式 / Two Ways to Define Tools

### 方式一：`@tool` 装饰器（推荐）

最简洁的方式，适合大多数场景：

```python
from pydantic import BaseModel, Field
from agent_harness import tool, ToolResult

# 第一步：定义输入参数（Pydantic 模型）
class ReadFileInput(BaseModel):
    path: str = Field(description="文件路径 / File path")
    encoding: str = Field(default="utf-8", description="编码 / Encoding")

# 第二步：用 @tool 装饰器定义工具
@tool(
    name="read_file",                    # 工具名称（模型用这个名字调用）
    description="读取文件内容 / Read file contents",  # 描述（帮模型理解何时使用）
    input_model=ReadFileInput,           # 参数模型
    is_read_only=True,                   # 只读操作（不修改系统状态）
    is_concurrency_safe=True,            # 可以和其他只读工具并发执行
)
async def read_file(input: ReadFileInput, context) -> ToolResult:
    """context 是 AgentContext，可以访问 metadata 等共享状态"""
    try:
        with open(input.path, encoding=input.encoding) as f:
            content = f.read()
        return ToolResult(content=content)
    except Exception as e:
        return ToolResult(content=f"Error: {e}", is_error=True)
```

**装饰器参数详解**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | str | 是 | 工具的唯一标识符。模型在 tool_calls 中使用这个名字 |
| `description` | str | 是 | 工具的功能描述。这是模型决定是否使用该工具的主要依据 |
| `input_model` | BaseModel | 是 | Pydantic 模型，定义工具接受的参数。会自动转为 JSON Schema 发给 LLM |
| `is_read_only` | bool | 否 | 默认 `False`。为 `True` 时表示此工具不会修改系统状态 |
| `is_concurrency_safe` | bool | 否 | 默认 `False`。为 `True` 时允许和其他安全工具并发执行 |

### 方式二：继承 `BaseTool`

需要更多控制时（自定义权限、复杂验证）：

```python
from agent_harness import BaseTool, ToolResult

class BashTool(BaseTool):
    name = "bash"
    description = "执行 shell 命令 / Execute a shell command"
    input_model = BashInput  # 你的 Pydantic 模型
    is_read_only = False
    is_concurrency_safe = False

    async def call(self, input: dict, context) -> ToolResult:
        parsed = BashInput.model_validate(input)
        # 执行命令...
        return ToolResult(content=stdout)

    async def check_permission(self, input: dict, context) -> bool:
        """自定义权限逻辑：比如禁止 rm -rf /"""
        parsed = BashInput.model_validate(input)
        if "rm -rf /" in parsed.command:
            return False
        return True
```

---

## Pydantic 输入模型详解 / Input Model Deep Dive

输入模型不仅用于参数验证，更重要的是它会**自动生成 JSON Schema 发送给 LLM**，让模型知道该传什么参数。

The input model is not just for validation — it **auto-generates JSON Schema sent to the LLM**, telling the model what parameters to pass.

```python
class SearchInput(BaseModel):
    query: str = Field(description="搜索关键词")
    max_results: int = Field(default=10, description="最大结果数", ge=1, le=100)
    case_sensitive: bool = Field(default=False, description="是否区分大小写")
```

自动生成的 JSON Schema（发给 LLM 的）：
```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string", "description": "搜索关键词"},
    "max_results": {"type": "integer", "description": "最大结果数", "minimum": 1, "maximum": 100, "default": 10},
    "case_sensitive": {"type": "boolean", "description": "是否区分大小写", "default": false}
  },
  "required": ["query"]
}
```

**要点**：
- `Field(description=...)` 写清楚，模型靠这个理解参数含义
- 有默认值的字段不会出现在 `required` 里
- 支持 Pydantic 所有验证器（`ge`, `le`, `regex` 等）

---

## ToolResult 返回值 / ToolResult

工具执行后必须返回 `ToolResult`：

```python
class ToolResult(BaseModel):
    content: str          # 返回给模型的文本内容
    is_error: bool        # 是否出错（模型会看到错误信息并尝试修正）
    context_updates: dict # 可选：更新 AgentContext.metadata 中的共享状态
```

**示例**：

```python
# 成功
return ToolResult(content="文件包含 42 行代码")

# 出错（模型会看到错误并可能重试）
return ToolResult(content="Error: 文件不存在", is_error=True)

# 成功 + 更新共享状态
return ToolResult(
    content="已读取 config.json",
    context_updates={"last_read_file": "config.json"},
)
```

---

## ToolRegistry 工具注册表 / Tool Registry

集中管理所有工具：

```python
from agent_harness import ToolRegistry

# 创建并注册
registry = ToolRegistry([read_file, bash_tool, search_tool])

# 按名查找
tool = registry.get("read_file")    # 返回工具实例或 None

# 检查是否存在
"bash" in registry                   # True / False

# 所有工具名
registry.names()                     # {"read_file", "bash", "search"}

# 转为 JSON Schema（发给 LLM）
definitions = registry.definitions() # list[ToolDefinition]

# 过滤（用于子 Agent）
read_only_tools = registry.filter(names={"read_file", "search"})
no_bash = registry.filter(exclude={"bash"})

# 工具数量
len(registry)                        # 3
```

**`filter()` 的意义**：当你创建子 Agent 时，通常不希望它拥有所有工具。比如"搜索 Agent" 只需要 grep 和 read_file，不需要 bash 和 write_file。`filter()` 创建一个新的 ToolRegistry 副本，只包含指定的工具。

---

## is_read_only 和 is_concurrency_safe 的作用 / Behavior Flags

这两个标记直接影响**工具编排策略**（详见 [04-orchestration.md](04-orchestration.md)）：

```
模型一次返回多个工具调用:
  tool_calls: [read_file("a.py"), read_file("b.py"), write_file("c.py")]

编排器分区:
  批次 1 (并发): read_file("a.py") + read_file("b.py")   ← 都是 read_only + concurrency_safe
  批次 2 (串行): write_file("c.py")                        ← 不是 read_only
```

| 标记 | 为 True 的含义 | 为 False 的含义（默认） |
|------|----------------|----------------------|
| `is_read_only` | 不修改任何状态（文件、数据库等） | 可能修改状态 |
| `is_concurrency_safe` | 可以和其他安全工具同时执行 | 必须独占执行 |

**安全原则**：默认都是 `False`（即假设工具有副作用、不能并发）。只有你确认安全时才设为 `True`。
