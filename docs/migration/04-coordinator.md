# v0.6.0 — Coordinator 多 Agent 编排

## 概述

当前 agent_harness 只有父子 Agent 关系 (SubAgent)。Coordinator 模式引入一个调度 Agent 分发任务给多个平级 worker Agent，实现真正的多 Agent 协作。

---

## 原始代码

📄 SOURCE: `src/coordinator/coordinatorMode.ts` (19,000 lines — 包含大量 UI/React 代码)
- ⚡ KEY FN: `isCoordinatorMode()` — 检测是否为 coordinator 模式
- ⚡ KEY FN: `matchSessionMode(sessionMode)` — 同步环境变量与会话模式
- ⚡ KEY FN: `getCoordinatorUserContext(mcpClients, scratchpadDir)` — 生成 worker 上下文字符串

### Coordinator 架构

```
Coordinator Agent (调度者)
  ├── 只有 3 个工具: Agent (创建 worker), SendMessage (继续 worker), TaskStop (停止)
  ├── 不直接执行任务
  └── 综合 worker 结果回答用户

Worker 1 (通用 Agent)
  ├── 完整工具集 (bash, read, write, edit, glob, grep, ...)
  └── 独立上下文，通过 task-notification 返回结果

Worker 2 (探索 Agent)
  ├── 只读工具集
  └── ...

Worker N ...
```

### Coordinator 系统提示词

📄 SOURCE: `src/constants/prompts.ts` — coordinator 相关部分
- ⚡ Coordinator 身份: "You are an orchestrator (not an implementer)"
- ⚡ 三个工具的使用指导
- ⚡ Worker 结果通过 `<task-notification>` XML 消息返回

### Worker 通信机制

- **创建**: Coordinator 调用 Agent 工具 → 生成独立进程/上下文
- **结果返回**: Worker 完成后，结果作为 `<task-notification>` 消息注入 Coordinator 会话
- **继续**: SendMessage 工具恢复已暂停的 worker
- **中止**: TaskStop 工具终止 worker

---

## Python 实现计划

🎯 TARGET: `agent_harness/coordinator/` (新目录)

```
agent_harness/coordinator/
├── __init__.py
├── coordinator.py      # CoordinatorLoop — 调度引擎
├── worker.py           # WorkerAgent — worker 封装
└── messages.py         # 消息路由与结果注入
```

### 核心类设计

```python
class CoordinatorLoop:
    """多 Agent 编排引擎。自己不执行工具，只调度 worker。"""

    def __init__(self, llm, workers_config, system_prompt=None):
        ...

    async def run(self, user_input: str) -> AsyncGenerator[CoordinatorEvent, None]:
        """运行 coordinator 循环：
        1. 接收用户请求
        2. 调用 LLM 决定分配哪些 worker
        3. 并行/串行启动 worker
        4. 收集 worker 结果
        5. 综合回答
        """

class WorkerAgent:
    """封装 SubAgent，添加 coordinator 通信协议"""

    def __init__(self, agent_type, tools, llm, ...):
        ...

    async def run(self, task: str) -> WorkerResult:
        ...
```

🎯 TARGET: `agent_harness/agent/context.py` (修改)
- 添加 `mode: Literal["default", "plan", "coordinator"] = "default"`

---

## 修改文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `agent_harness/coordinator/__init__.py` | Coordinator 模块 |
| 新建 | `agent_harness/coordinator/coordinator.py` | 调度引擎 |
| 新建 | `agent_harness/coordinator/worker.py` | Worker 封装 |
| 新建 | `agent_harness/coordinator/messages.py` | 消息路由 |
| 修改 | `agent_harness/agent/context.py` | mode 枚举扩展 |
| 修改 | `agent_harness/__init__.py` | 导出新类 |
| 新建 | `test_coordinator.py` | 测试 |
| 修改 | `pyproject.toml` + `__init__.py` | 版本 → 0.6.0 |
