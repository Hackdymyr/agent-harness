# 10 LangGraph 集成 / LangGraph Integration

## 概述 / Overview

`as_langgraph_node()` 将 `agent_harness` 的 Agent 包装成一个 LangGraph 兼容的节点函数。这样你可以用 LangGraph 做多 Agent 编排，同时用 agent_harness 做每个 Agent 内部的工具循环。

`as_langgraph_node()` wraps an agent_harness Agent into a LangGraph-compatible node function. Use LangGraph for multi-agent orchestration, and agent_harness for each agent's internal tool loop.

---

## 定位 / Positioning

```
┌───────────────────────────────────────────────┐
│                LangGraph                       │
│  负责: Agent 之间的路由、状态传递、条件分支        │
│  Handles: routing, state passing, branching    │
│                                                │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│  │ Agent A   │───→│ Agent B   │───→│ Agent C   │ │
│  │ (node)    │    │ (node)    │    │ (node)    │ │
│  └──────────┘    └──────────┘    └──────────┘ │
│       ↑               ↑               ↑       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│  │ agent_    │    │ agent_    │    │ agent_    │ │
│  │ harness   │    │ harness   │    │ harness   │ │
│  │ 工具循环   │    │ 工具循环   │    │ 工具循环   │ │
│  └──────────┘    └──────────┘    └──────────┘ │
└───────────────────────────────────────────────┘
```

---

## 基本用法 / Basic Usage

```python
from agent_harness import as_langgraph_node, OpenAICompatLLM

# 创建节点
coder_node = as_langgraph_node(
    llm=OpenAICompatLLM(base_url="...", model="...", api_key="..."),
    tools=[read_file, write_file, bash],
    system_prompt="你是一个专业的 Python 开发者。",
    max_turns=30,
)
```

---

## 接入 LangGraph / Using with LangGraph

```python
from langgraph.graph import StateGraph, END

# 定义多个 Agent 节点
coder = as_langgraph_node(
    llm=llm,
    tools=[read_file, write_file, bash],
    system_prompt="你是开发者，编写代码解决问题。",
)

reviewer = as_langgraph_node(
    llm=llm,
    tools=[read_file],
    system_prompt="你是代码审查者，检查代码质量和潜在问题。",
)

tester = as_langgraph_node(
    llm=llm,
    tools=[bash],
    system_prompt="你是测试工程师，编写和运行测试。",
)

# 构建图
graph = StateGraph(dict)
graph.add_node("coder", coder)
graph.add_node("reviewer", reviewer)
graph.add_node("tester", tester)

graph.set_entry_point("coder")
graph.add_edge("coder", "reviewer")
graph.add_edge("reviewer", "tester")
graph.add_edge("tester", END)

app = graph.compile()

# 运行
result = await app.ainvoke({
    "input": "实现一个斐波那契数列函数",
    "messages": [],
})
print(result["output"])
```

---

## State 约定 / State Contract

`as_langgraph_node()` 返回的节点函数签名是 `async def node(state: dict) -> dict`。

### 输入 State

| 键 Key | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `input` | str | 是 | 本节点的用户输入/任务描述 |
| `messages` | list[dict] | 否 | 之前的消息历史（跨节点传递上下文） |

### 输出 State

| 键 Key | 类型 | 说明 |
|--------|------|------|
| `output` | str | 本节点 Agent 的最终文本回复 |
| `messages` | list[dict] | 更新后的完整消息历史 |

---

## 参数详解 / Parameters

```python
node = as_langgraph_node(
    llm=...,                              # BaseLLM 实例（必填）
    tools=[tool1, tool2],                  # 工具列表（可选，默认无工具）
    system_prompt="你是...",                # 系统提示（可选）
    permission_mode=PermissionMode.AUTO_ALLOW,  # 权限模式（默认全部允许）
    max_turns=50,                          # 最大循环轮数
    max_tokens=4096,                       # LLM 最大输出 token
)
```

---

## 不用 LangGraph 也能多 Agent / Multi-Agent without LangGraph

如果你不想引入 LangGraph 依赖，可以手动编排：

```python
from agent_harness import AgentLoop, AgentContext, ToolRegistry

async def run_pipeline(task: str):
    # Agent 1: 编码
    ctx1 = AgentContext(messages=[], tools=coder_tools, llm=llm, system_prompt="你是开发者")
    code_result = await AgentLoop(ctx1).run_to_completion(task)

    # Agent 2: 审查（把 Agent 1 的结果作为输入）
    ctx2 = AgentContext(messages=[], tools=reviewer_tools, llm=llm, system_prompt="你是审查者")
    review_result = await AgentLoop(ctx2).run_to_completion(
        f"请审查以下代码:\n{code_result.content}"
    )

    return review_result.content
```

这种方式更简单直接，适合线性流水线。LangGraph 的优势在于条件分支、循环、并行等复杂拓扑。
