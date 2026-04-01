# agent_harness 文档 / Documentation

欢迎阅读 agent_harness 的完整文档。本文档面向**不借助 AI 也能独立理解和使用本库**的开发者。

Welcome to the full documentation for agent_harness. This documentation is written so that developers can understand and use the library **independently, without AI assistance**.

---

## 文档目录 / Table of Contents

| 文档 Document | 内容 Content |
|---|---|
| [01-concepts.md](01-concepts.md) | 核心概念与架构总览 / Core concepts & architecture overview |
| [02-llm-adapters.md](02-llm-adapters.md) | LLM 适配器：如何接入不同模型 / LLM adapters: connecting different models |
| [03-tools.md](03-tools.md) | 工具系统：定义、注册、装饰器 / Tool system: definition, registry, decorator |
| [04-orchestration.md](04-orchestration.md) | 工具编排：并发与串行执行 / Tool orchestration: concurrent & serial execution |
| [05-permissions.md](05-permissions.md) | 权限系统 / Permission system |
| [06-agent-loop.md](06-agent-loop.md) | Agent 循环：核心引擎详解 / Agent loop: core engine deep dive |
| [07-sub-agent.md](07-sub-agent.md) | 子 Agent：上下文隔离与生成 / Sub-agent: context isolation & spawning |
| [08-tasks.md](08-tasks.md) | 任务追踪 / Task tracking |
| [09-memory.md](09-memory.md) | 持久记忆 / Persistent memory |
| [10-langgraph.md](10-langgraph.md) | LangGraph 集成 / LangGraph integration |
| [11-cookbook.md](11-cookbook.md) | 实战示例合集 / Practical examples cookbook |

---

## 快速导航 / Quick Navigation

**我想…… / I want to……**

- 快速跑一个 Agent → [06-agent-loop.md](06-agent-loop.md) 的"最小示例"
- 接入自己的模型 → [02-llm-adapters.md](02-llm-adapters.md)
- 给 Agent 添加工具 → [03-tools.md](03-tools.md)
- 理解并发执行逻辑 → [04-orchestration.md](04-orchestration.md)
- 搭建多 Agent 团队 → [10-langgraph.md](10-langgraph.md)
- 看完整实战例子 → [11-cookbook.md](11-cookbook.md)
