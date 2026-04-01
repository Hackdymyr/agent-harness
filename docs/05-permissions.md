# 05 权限系统 / Permission System

## 概述 / Overview

权限系统控制 Agent 是否有权执行某个工具。这是安全的关键——你不希望 Agent 未经确认就删除文件或执行危险命令。

The permission system controls whether an agent is allowed to execute a tool. This is critical for safety — you don't want agents deleting files or running dangerous commands without confirmation.

---

## 三种模式 / Three Modes

### `AUTO_ALLOW` — 全部自动通过

```python
from agent_harness import PermissionChecker, PermissionMode

checker = PermissionChecker(default_mode=PermissionMode.AUTO_ALLOW)
```

**行为**：所有工具都自动通过，不需要确认。

**适用场景**：
- 开发/测试环境
- 所有工具都是安全的（只读操作）
- 你完全信任 Agent 的行为

### `ASK_USER` — 写入操作需要确认

```python
async def confirm(tool_name: str, description: str, input: dict) -> bool:
    """这个函数在工具需要权限时被调用"""
    answer = input(f"允许执行 {tool_name}? (y/n): ")
    return answer.lower() == "y"

checker = PermissionChecker(
    default_mode=PermissionMode.ASK_USER,
    ask_callback=confirm,  # 你的确认函数
)
```

**行为**：
- `is_read_only=True` 的工具 → 自动通过
- 其他工具 → 调用 `ask_callback`，由用户决定
- 如果没有设置 `ask_callback` → 默认拒绝

**适用场景**：
- 生产环境
- Agent 有写入/删除能力时
- 需要人工审核关键操作

### `DENY_NON_READONLY` — 只允许只读

```python
checker = PermissionChecker(default_mode=PermissionMode.DENY_NON_READONLY)
```

**行为**：
- `is_read_only=True` 的工具 → 通过
- 其他所有工具 → 拒绝

**适用场景**：
- "只看不动"模式
- 代码审查 Agent（只需要读代码，不需要修改）
- 安全敏感环境

---

## 每工具规则覆盖 / Per-Tool Rule Overrides

全局模式之外，你可以对特定工具设置不同的规则：

```python
from agent_harness import PermissionRule

checker = PermissionChecker(
    default_mode=PermissionMode.ASK_USER,  # 默认需要问
    rules=[
        # read_file 总是允许（即使全局模式是 ASK_USER）
        PermissionRule(tool_name="read_file", mode=PermissionMode.AUTO_ALLOW),

        # bash 总是拒绝（即使全局模式是 AUTO_ALLOW）
        PermissionRule(tool_name="bash", mode=PermissionMode.DENY_NON_READONLY),
    ],
)
```

**优先级**：每工具规则 > 全局模式

---

## ask_callback 详解 / ask_callback Deep Dive

`ask_callback` 是一个异步函数，签名如下：

```python
async def ask_callback(
    tool_name: str,      # 工具名称，如 "bash"
    description: str,    # 工具描述，如 "执行 shell 命令"
    input: dict,         # 工具输入参数，如 {"command": "rm -rf /tmp/old"}
) -> bool:               # True = 允许, False = 拒绝
```

**示例——GUI 弹窗确认**：

```python
async def gui_confirm(tool_name, description, input):
    import tkinter.messagebox as mb
    msg = f"Agent 想执行:\n工具: {tool_name}\n参数: {input}"
    return mb.askyesno("权限确认", msg)
```

**示例——基于规则自动判断**：

```python
async def smart_confirm(tool_name, description, input):
    # bash 工具：只允许安全命令
    if tool_name == "bash":
        cmd = input.get("command", "")
        dangerous = ["rm ", "dd ", "mkfs", "chmod 777"]
        return not any(d in cmd for d in dangerous)
    # 其他写入工具：总是允许
    return True
```

**示例——日志记录 + 自动通过**：

```python
async def log_and_allow(tool_name, description, input):
    print(f"[AUDIT] {tool_name} called with {input}")
    return True
```

---

## 工具自身的权限检查 / Tool-Level Permission Check

除了全局的 `PermissionChecker`，每个工具还有自己的 `check_permission()` 方法：

```python
class SafeBashTool(BaseTool):
    name = "bash"
    # ...

    async def check_permission(self, input: dict, context) -> bool:
        """工具级权限：禁止危险命令"""
        cmd = input.get("command", "")
        if "rm -rf" in cmd:
            return False
        return True
```

**执行顺序**：
```
1. PermissionChecker.check()      ← 全局权限（模式 + 规则）
   ↓ 通过
2. tool.check_permission()         ← 工具自身权限
   ↓ 通过
3. tool.call()                     ← 实际执行
```

两层都通过才会执行。
