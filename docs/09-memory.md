# 09 持久记忆 / Persistent Memory

## 概述 / Overview

`FileMemoryStore` 提供基于文件的持久化记忆存储。每条记忆是一个 Markdown 文件，带有 YAML frontmatter 元数据。Agent 重启后记忆仍在。

`FileMemoryStore` provides file-based persistent memory. Each memory entry is a Markdown file with YAML frontmatter metadata. Memories survive agent restarts.

---

## 存储格式 / Storage Format

每条记忆存储为一个 `.md` 文件：

```markdown
---
name: user_preferences
description: 用户的编码偏好
type: feedback
---

用户偏好使用函数式编程风格，不喜欢 OOP。
测试框架偏好 pytest。
缩进用 4 空格。
```

- `---` 之间是 YAML frontmatter（元数据）
- `---` 之后是正文内容

---

## 基本用法 / Basic Usage

```python
from agent_harness import FileMemoryStore

# 创建存储（指定目录，不存在会自动创建）
store = FileMemoryStore(".agent_memory")

# 写入
store.write(
    name="user_role",                        # 记忆名称（也是文件名）
    content="用户是高级 Python 开发者，专注后端",  # 正文内容
    metadata={                                # frontmatter 元数据
        "name": "user_role",
        "description": "用户角色和技术背景",
        "type": "user",
    },
)

# 读取
entry = store.read("user_role")
print(entry.name)      # "user_role"
print(entry.content)   # "用户是高级 Python 开发者，专注后端"
print(entry.metadata)  # {"name": "user_role", "description": "...", "type": "user"}
print(entry.path)      # ".agent_memory/user_role.md"

# 不存在的记忆
entry = store.read("nonexistent")  # None

# 列出所有记忆
entries = store.list()  # list[MemoryEntry]

# 搜索（大小写不敏感的子串匹配）
results = store.search("Python")
# 搜索范围：name + content + metadata values

# 删除
store.delete("user_role")  # True（成功删除）
store.delete("nonexistent")  # False（不存在）
```

---

## MemoryEntry 数据结构 / Data Structure

```python
@dataclass
class MemoryEntry:
    name: str               # 记忆名称
    path: str               # 文件路径
    content: str            # 正文内容（frontmatter 之后的部分）
    metadata: dict[str, Any] # frontmatter 中的键值对
```

---

## 推荐的记忆分类 / Recommended Memory Types

沿用 Claude Code 的四类记忆体系：

| type | 用途 | 示例 |
|------|------|------|
| `user` | 用户信息：角色、偏好、知识水平 | "用户是数据科学家，熟悉 pandas" |
| `feedback` | 行为指导：该做/不该做什么 | "不要在测试中 mock 数据库" |
| `project` | 项目动态：目标、进度、决策 | "正在将认证从 session 迁移到 JWT" |
| `reference` | 外部资源指针：文档、看板、工具 | "bug 追踪在 Linear 的 INGEST 项目" |

---

## 实际应用场景 / Practical Scenarios

### 让 Agent 记住用户偏好

```python
# Agent 在对话中学到用户偏好后，保存到记忆
store.write("feedback_code_style", "用户要求：\n- 不加 type hints\n- 不写 docstring\n- 变量名用 snake_case", {
    "type": "feedback",
    "description": "用户的代码风格偏好",
})

# 下次启动 Agent 时，读取记忆注入 system_prompt
memories = store.list()
memory_text = "\n".join(f"[{e.metadata.get('type', 'info')}] {e.content}" for e in memories)
system_prompt = f"你是代码助手。\n\n以下是你需要记住的信息：\n{memory_text}"
```

### 跨会话持久化项目上下文

```python
# 第一次会话结束时
store.write("project_status", "已完成认证模块，下一步是写测试", {
    "type": "project",
    "description": "项目当前状态",
})

# 第二次会话开始时
status = store.read("project_status")
if status:
    print(f"上次进度: {status.content}")
```

---

## 文件名安全处理 / Filename Sanitization

记忆名称中的特殊字符会被替换为 `_`：

```python
store.write("user/preferences!@#", "...")
# 实际文件名: .agent_memory/user_preferences___.md
```

允许的字符：字母、数字、下划线、连字符、点。
