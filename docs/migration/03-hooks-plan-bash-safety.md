# v0.5.0 — Hook 系统 + Plan 模式 + Bash 安全校验

## 概述

三个相关功能打包在一个版本中：
1. **Hook 系统** — 工具调用前后执行用户定义的回调/命令
2. **Plan 模式** — 探索→规划→审批→实施的工作流
3. **Bash 命令安全校验** — 白名单校验 bash 命令的危险性

---

## 一、Hook 系统

### 原始代码

📄 SOURCE: `src/utils/hooks/hooksConfigManager.ts`
- ⚡ 定义了 26 种 hook 事件类型
- ⚡ KEY FN: `groupHooksByEventAndMatcher()` — hook 按事件/匹配器分组
- ⚡ KEY FN: `getHookEventMetadata()` — 所有事件的元数据

📄 SOURCE: `src/utils/hooks/hooksSettings.ts`
- ⚡ KEY FN: 从 settings.json 加载 hook 配置
- ⚡ hook 相等性检查

📄 SOURCE: `src/utils/hooks/sessionHooks.ts`
- ⚡ KEY FN: `addSessionHook()` — 注册会话级 hook
- ⚡ KEY FN: `addFunctionHook()` — 注册函数级 hook
- ⚡ 会话级 hook 只在内存中，不持久化

📄 SOURCE: `src/utils/hooks/hookEvents.ts`
- ⚡ hook 事件发射系统 (fire-and-forget + pending queue)

📄 SOURCE: `src/utils/hooks/hooks.ts`
- ⚡ KEY FN: `executeHook()` — shell 命令 hook 执行

📄 SOURCE: `src/utils/hooks/execPromptHook.ts`
- ⚡ LLM 提示词 hook 执行 (使用轻量模型)

📄 SOURCE: `src/utils/hooks/execHttpHook.ts`
- ⚡ HTTP API hook 执行

📄 SOURCE: `src/utils/hooks/execAgentHook.ts`
- ⚡ Agent hook 执行 (子 agent)

### Hook 事件类型 (26 种)

```
PreToolUse, PostToolUse, PostToolUseFailure, PermissionDenied,
Notification, UserPromptSubmit, SessionStart, SessionEnd,
Stop, StopFailure, SubagentStart, SubagentStop,
PreCompact, PostCompact, PermissionRequest, Setup,
TeammateIdle, TaskCreated, TaskCompleted,
Elicitation, ElicitationResult, ConfigChange,
InstructionsLoaded, WorktreeCreate, WorktreeRemove,
CwdChanged, FileChanged
```

### 配置格式 (settings.json)

```json
{
  "hooks": [
    {
      "event": "PreToolUse",
      "matcher": "Bash",
      "type": "command",
      "command": "echo 'About to run bash'"
    },
    {
      "event": "PostToolUse",
      "type": "prompt",
      "prompt": "Summarize what just happened"
    },
    {
      "event": "PreToolUse",
      "type": "http",
      "url": "https://webhook.example.com/approve"
    }
  ]
}
```

### Python 实现计划

🎯 TARGET: `agent_harness/hooks/` (新目录)

```
agent_harness/hooks/
├── __init__.py
├── types.py           # HookEvent enum, HookConfig dataclass
├── registry.py        # HookRegistry — 注册/查找/执行
└── executor.py        # 各类型 hook 执行器 (command/callback)
```

**简化策略:** 初版只实现 command 和 callback 两种 hook 类型。
- command: 执行 shell 命令
- callback: 执行 Python async callable

跳过: prompt hook (需要 LLM 调用)、http hook、agent hook — 可在后续版本添加。

初版 hook 事件精简为:
```
PreToolUse, PostToolUse, PreCompact, PostCompact, SessionStart, SessionEnd
```

🎯 TARGET: `agent_harness/tools/orchestration.py` (修改)
- `_execute_single()` 中在工具调用前后触发 hook

---

## 二、Plan 模式

### 原始代码

📄 SOURCE: `src/tools/EnterPlanModeTool/EnterPlanModeTool.ts`
- ⚡ KEY FN: `call()` — 切换到 plan 模式
- ⚡ KEY FN: `prepareContextForPlanMode()` — 准备 plan 模式上下文
- ⚡ 行为: 设置 mode='plan'，限制为只读操作

📄 SOURCE: `src/tools/EnterPlanModeTool/prompt.ts`
- ⚡ 详细的使用指导: 何时使用/不使用, plan 模式中的行为

📄 SOURCE: `src/tools/ExitPlanModeTool/ExitPlanModeV2Tool.ts`
- ⚡ KEY FN: `call()` — 退出 plan 模式
- ⚡ KEY FN: `getPlan()` — 从磁盘读取 plan 文件
- ⚡ Input: `{ allowedPrompts?: AllowedPrompt[] }` — 实施计划所需的权限

📄 SOURCE: `src/tools/ExitPlanModeTool/prompt.ts`
- ⚡ 退出 plan 模式的指导

### Plan 文件存储

```
~/.claude/plans/<session-id-slug>.md
```

### Python 实现计划

🎯 TARGET: `agent_harness/plan/` (新目录)

```
agent_harness/plan/
├── __init__.py
├── mode.py            # PlanMode 状态管理
└── tools.py           # EnterPlanTool, ExitPlanTool 内置工具
```

🎯 TARGET: `agent_harness/agent/context.py` (修改)
- 添加 `mode: Literal["default", "plan"] = "default"`
- plan 模式下限制工具为只读

---

## 三、Bash 命令安全校验

### 原始代码

📄 SOURCE: `src/utils/shell/readOnlyCommandValidation.ts` (68,300 lines — 大量为命令白名单数据)

**关键数据结构:**

```typescript
type FlagArgType = 'none' | 'number' | 'string' | 'char' | '{}' | 'EOF'

type ExternalCommandConfig = {
    safeFlags: Record<string, FlagArgType>
    additionalCommandIsDangerousCallback?: (rawCommand, args) => boolean
    respectsDoubleDash?: boolean
}
```

**安全命令白名单:**
- Git 只读: `log, show, diff, status, branch, tag, ls-files, ls-tree, rev-parse, cat-file, show-ref`
- 系统只读: `find, grep, ls, cat, head, tail, stat, file, wc, sort, uniq, du, df`
- gh 只读: `pr list, pr view, issue list, issue view, api`

**危险模式:**
- 文件修改: `rm, mv, cp, chmod, chown, mkdir`
- 进程控制: `kill, pkill, sudo`
- 写重定向: `>`, `>>`, `|`
- UNC 路径: `//server/share` (凭据泄露风险)

### Python 实现计划

🎯 TARGET: `agent_harness/builtins/bash_safety.py` (新建)

```python
class CommandSafety(Enum):
    SAFE = "safe"           # 白名单命令
    UNKNOWN = "unknown"     # 未知命令
    DANGEROUS = "dangerous" # 明确危险

READONLY_COMMANDS: dict[str, CommandConfig] = {
    "git log": ..., "git diff": ..., "git status": ...,
    "ls": ..., "cat": ..., "find": ..., "grep": ...,
    ...
}

DANGEROUS_PATTERNS: list[str] = [
    "rm ", "rm\t", "sudo ", "> ", ">> ", ...
]

def classify_command(command: str) -> CommandSafety:
    """分类 bash 命令的安全性"""

def is_read_only_command(command: str) -> bool:
    """检查命令是否为只读操作"""
```

🎯 TARGET: `agent_harness/builtins/bash_tool.py` (修改)
- 在 `call()` 中添加 `classify_command()` 检查
- plan 模式下拒绝非只读命令

---

## 修改文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `agent_harness/hooks/__init__.py` | Hook 模块 |
| 新建 | `agent_harness/hooks/types.py` | HookEvent, HookConfig |
| 新建 | `agent_harness/hooks/registry.py` | Hook 注册与查找 |
| 新建 | `agent_harness/hooks/executor.py` | Hook 执行器 |
| 新建 | `agent_harness/plan/__init__.py` | Plan 模块 |
| 新建 | `agent_harness/plan/mode.py` | Plan 模式状态 |
| 新建 | `agent_harness/plan/tools.py` | Plan 模式工具 |
| 新建 | `agent_harness/builtins/bash_safety.py` | 命令安全校验 |
| 修改 | `agent_harness/tools/orchestration.py` | 集成 hook 触发 |
| 修改 | `agent_harness/agent/context.py` | 添加 mode 字段 |
| 修改 | `agent_harness/builtins/bash_tool.py` | 集成安全校验 |
| 新建 | `test_hooks_plan_safety.py` | 测试 |
| 修改 | `pyproject.toml` + `__init__.py` | 版本 → 0.5.0 |
