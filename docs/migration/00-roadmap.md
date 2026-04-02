# agent_harness 功能迁移路线图

> 从 Claude Code (TypeScript) 迁移核心功能到 agent_harness (Python)
> Claude Code 源码位置: `D:/claude_project/Claude copy/claude-code-main/src/`
> agent_harness 位置: `D:/claude_project/Claude copy/agent_harness/`

## 版本规划

| 版本 | 功能 | 状态 | 文档 |
|------|------|------|------|
| v0.1.0 | 核心架构 (AgentLoop, Tools, Permissions, SubAgent, Memory, Tasks, LangGraph) | ✅ 已完成 | — |
| v0.2.0 | 富提示词工程 (SystemPromptBuilder, AgentType, Rich Tool Descriptions) | ✅ 已完成 | — |
| **v0.3.0** | **API 重试 + 流式输出** | ✅ 已完成 | [01-retry-streaming.md](01-retry-streaming.md) |
| **v0.4.0** | **上下文压缩 (Compaction)** | ⬜ 待开始 | [02-compaction.md](02-compaction.md) |
| **v0.5.0** | **Hook 系统 + Plan 模式 + Bash 安全校验** | ⬜ 待开始 | [03-hooks-plan-bash-safety.md](03-hooks-plan-bash-safety.md) |
| **v0.6.0** | **Coordinator 多 Agent 编排** | ⬜ 待开始 | [04-coordinator.md](04-coordinator.md) |
| **v0.7.0** | **MCP 客户端集成** | ⬜ 待开始 | [05-mcp-client.md](05-mcp-client.md) |
| **v0.8.0** | **Skill 系统 + 会话持久化** | ⬜ 待开始 | [06-skills-session.md](06-skills-session.md) |

## 不迁移的功能

| 功能 | 原因 |
|------|------|
| Ink 终端渲染 (252K LOC) | 纯 UI 层，library 不需要 |
| React 组件/Hooks | UI 框架耦合 |
| IDE Bridge (100K+ LOC) | VS Code/JetBrains 集成，属于上层应用 |
| Voice 集成 | 输入方式，不属于 agent 核心 |
| Vim 快捷键 | 终端 UI 功能 |
| Desktop/Electron | 桌面应用壳 |
| Chrome 扩展 | 浏览器集成 |
| Buddy 伴侣动画 | 纯 UI 趣味功能 |
| OAuth 认证流 | Anthropic 特有认证 |
| 100+ CLI 命令 | agent_harness 是 library 不是 CLI |
| Analytics/Datadog | SaaS 产品遥测 |
| Auto-update | CLI 分发机制 |
| ANSI-to-PNG (215K LOC) | 截图渲染 |
| Team/Swarm | 太新太复杂，价值未验证 |

## 约定

- 每个版本对应一个迁移文档 `docs/migration/0N-xxx.md`
- 文档中标记 `📄 SOURCE:` 指向 Claude Code 原始文件的**完整路径**
- 文档中标记 `🎯 TARGET:` 指向 agent_harness 中要创建/修改的文件
- 文档中标记 `⚡ KEY FN:` 列出原始代码中的关键函数名和行号
- 开始新版本前先读对应迁移文档，按文档中的源码标记找到代码即可开工
