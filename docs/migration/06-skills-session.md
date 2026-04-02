# v0.8.0 — Skill 系统 + 会话持久化

## 概述

1. **Skill 系统** — 可复用的提示词+工具+工作流模板，从 SKILL.md 文件加载
2. **会话持久化** — 将对话历史、任务、元数据保存到磁盘，支持恢复

---

## 一、Skill 系统

### 原始代码

📄 SOURCE: `src/skills/loadSkillsDir.ts` (1,087 lines — 去除 bundled 后)
- ⚡ KEY FN: `getSkillDirCommands(cwd)` — 加载所有 skills，去重
- ⚡ KEY FN: `loadSkillsFromSkillsDir()` — 从 /skills/ 目录加载
- ⚡ KEY FN: `discoverSkillDirsForPaths()` — 文件操作时动态发现 skills
- ⚡ KEY FN: `activateConditionalSkillsForPaths()` — 路径过滤激活
- ⚡ KEY FN: `parseSkillFrontmatterFields()` — 解析 YAML frontmatter

📄 SOURCE: `src/skills/bundledSkills.ts` (7,500 lines)
- ⚡ 17 个内置 skill 定义

📄 SOURCE: `src/skills/mcpSkillBuilders.ts` (1,600 lines)
- ⚡ MCP skill 集成

📄 SOURCE: `src/tools/SkillTool/SkillTool.ts`
- ⚡ Skill 调用工具实现

📄 SOURCE: `src/tools/SkillTool/prompt.ts`
- ⚡ Skill 使用指导提示词

📄 SOURCE: `src/tools/SkillTool/constants.ts`
- ⚡ SKILL_TOOL_NAME = 'Skill'

### SKILL.md 文件格式

```markdown
---
name: skill-name
description: What the skill does
user-invocable: true
allowed-tools: [Bash, FileRead, FileEdit]
arguments: [arg1, arg2]
when-to-use: Context for when LLM should auto-activate
version: 1.0.0
effort: low|medium|high
context: fork|inline
paths: |
  src/**/*.js
  tests/**/*.ts
hooks:
  PreToolUse:
    - command: "echo $ARGUMENTS"
---

## Skill Instructions

Actual instructions for the LLM go here.
Supports ${ARGUMENTS} variable substitution.
Supports !`command` for inline shell execution.
Supports ${CLAUDE_SKILL_DIR} for skill directory reference.
```

### Skill 发现优先级

```
1. managed: ~/.claude/managed/.claude/skills   (最高)
2. user:    ~/.claude/skills
3. project: ./.claude/skills (cwd 及父目录向上查找)
4. additional: --add-dir 指定的路径
5. legacy:  ./.commands/ (已废弃)                (最低)
```

去重: 基于 realpath()，先发现的优先。

---

## Python 实现计划

🎯 TARGET: `agent_harness/skills/` (新目录)

```
agent_harness/skills/
├── __init__.py
├── loader.py           # Skill 发现与加载
├── skill.py            # Skill 数据模型
├── executor.py         # Skill 执行 (变量替换, 工具限制)
└── tool.py             # InvokeSkillTool 内置工具
```

### Skill 数据模型

```python
@dataclass
class Skill:
    name: str
    description: str
    instructions: str  # frontmatter 之后的 markdown 内容
    allowed_tools: list[str] | None = None  # None = 所有
    arguments: list[str] | None = None
    when_to_use: str | None = None
    user_invocable: bool = False
    context: Literal["fork", "inline"] = "inline"
    paths: list[str] | None = None  # gitignore 风格路径过滤
    source_path: str = ""  # SKILL.md 文件路径

class SkillRegistry:
    def load_from_directory(path: str) -> None: ...
    def discover(cwd: str) -> None: ...
    def get(name: str) -> Skill | None: ...
    def list_user_invocable() -> list[Skill]: ...
    def match_for_paths(paths: list[str]) -> list[Skill]: ...
```

---

## 二、会话持久化

### 原始代码

📄 SOURCE: `src/utils/sessionStorage.ts` (5,105 lines — 大文件)
- ⚡ KEY FN: `saveMode()` — 保存权限模式
- ⚡ KEY FN: `adoptResumedSessionFile()` — 恢复持久化状态
- ⚡ KEY FN: `recordContentReplacement()` — 记录编辑操作
- ⚡ KEY FN: `resetSessionFilePointer()` — 重置追踪

📄 SOURCE: `src/utils/sessionRestore.ts` (551 lines)
- ⚡ KEY FN: `extractTodosFromTranscript()` — 提取任务列表
- ⚡ KEY FN: `restoreAttributionStateFromSnapshots()` — 恢复归属状态
- ⚡ KEY FN: `restoreWorktreeSession()` — 恢复 worktree

### 持久化内容

```
persisted:
  1. messages         — 完整对话 transcript
  2. tool_results     — 缓存的工具执行结果
  3. file_history     — 文件操作记录
  4. metadata         — 会话名称、模式、项目目录
  5. tasks            — 任务列表
  6. mode             — 权限模式 (default|plan|auto)
```

### 存储格式

```
JSONL (JSON Lines) — 每行一条记录
路径: ~/.claude/sessions/<session-id>/transcript.jsonl
```

---

## Python 实现计划

🎯 TARGET: `agent_harness/session/` (新目录)

```
agent_harness/session/
├── __init__.py
├── storage.py          # SessionStorage — JSONL 读写
└── restore.py          # SessionRestore — 恢复逻辑
```

### 核心 API

```python
class SessionStorage:
    def __init__(self, session_dir: str):
        self.path = Path(session_dir) / "transcript.jsonl"

    def save_message(self, message: dict) -> None: ...
    def save_metadata(self, key: str, value: Any) -> None: ...
    def load_transcript() -> list[dict]: ...
    def load_metadata() -> dict: ...

class SessionManager:
    def create_session() -> str: ...      # 返回 session_id
    def resume_session(session_id: str) -> AgentContext: ...
    def list_sessions() -> list[SessionInfo]: ...
```

🎯 TARGET: `agent_harness/agent/loop.py` (修改)
- 可选 `session_storage: SessionStorage | None`
- 每轮消息自动追加到 JSONL

---

## 修改文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `agent_harness/skills/__init__.py` | Skill 模块 |
| 新建 | `agent_harness/skills/loader.py` | Skill 发现与加载 |
| 新建 | `agent_harness/skills/skill.py` | Skill 数据模型 |
| 新建 | `agent_harness/skills/executor.py` | Skill 执行 |
| 新建 | `agent_harness/skills/tool.py` | InvokeSkillTool |
| 新建 | `agent_harness/session/__init__.py` | Session 模块 |
| 新建 | `agent_harness/session/storage.py` | JSONL 存储 |
| 新建 | `agent_harness/session/restore.py` | 恢复逻辑 |
| 修改 | `agent_harness/agent/loop.py` | 集成会话持久化 |
| 修改 | `agent_harness/__init__.py` | 导出 |
| 修改 | `pyproject.toml` | 版本 → 0.8.0 |
| 新建 | `test_skills_session.py` | 测试 |
