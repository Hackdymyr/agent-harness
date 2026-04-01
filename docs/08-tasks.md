# 08 任务追踪 / Task Tracking

## 概述 / Overview

`TaskTracker` 是一个内存中的任务列表，支持依赖关系（A 完成前 B 不能开始）。适合 Agent 将复杂工作分解为多个步骤并跟踪进度。

`TaskTracker` is an in-memory task list with dependency support (B can't start until A is done). Suitable for agents breaking complex work into tracked steps.

---

## 基本用法 / Basic Usage

```python
from agent_harness import TaskTracker, TaskStatus

tracker = TaskTracker()

# 创建任务
t1 = tracker.create("实现用户认证", description="添加 JWT token 验证")
t2 = tracker.create("编写单元测试", description="覆盖所有 API 端点")
t3 = tracker.create("部署到测试环境", blocked_by=[t1.id, t2.id])  # 依赖 t1 和 t2

print(t1.id)       # "task_a1b2c3d4"
print(t1.status)   # TaskStatus.PENDING
print(t3.blocked_by)  # [t1.id, t2.id]
```

---

## Task 数据结构 / Task Data Structure

```python
@dataclass
class Task:
    id: str                          # 自动生成，如 "task_a1b2c3d4"
    subject: str                     # 任务标题
    description: str = ""            # 详细描述
    status: TaskStatus = PENDING     # pending / in_progress / completed
    blocks: list[str] = []           # 本任务阻塞了哪些任务的 ID
    blocked_by: list[str] = []       # 哪些任务阻塞了本任务
    metadata: dict = {}              # 自定义元数据
```

---

## 状态流转 / Status Lifecycle

```
PENDING  ──→  IN_PROGRESS  ──→  COMPLETED
  创建时        开始工作时         完成时
```

```python
tracker.update(t1.id, status=TaskStatus.IN_PROGRESS)  # 开始
tracker.update(t1.id, status=TaskStatus.COMPLETED)     # 完成
```

---

## 依赖关系 / Dependencies

### 创建时声明

```python
t1 = tracker.create("设计数据库 schema")
t2 = tracker.create("编写迁移脚本", blocked_by=[t1.id])
t3 = tracker.create("填充测试数据", blocked_by=[t2.id])
```

### 创建后添加

```python
tracker.update(t3.id, add_blocked_by=[t1.id])  # t3 现在也依赖 t1
tracker.update(t1.id, add_blocks=[t4.id])       # t1 现在也阻塞 t4
```

### 检查阻塞状态

```python
tracker.is_blocked(t2.id)  # True — t1 还没完成
tracker.is_blocked(t1.id)  # False — 没有依赖

# 完成 t1
tracker.update(t1.id, status=TaskStatus.COMPLETED)
tracker.is_blocked(t2.id)  # False — t1 已完成，t2 解除阻塞
```

### 获取可执行任务

```python
available = tracker.available()
# 返回所有 status=PENDING 且不被任何未完成任务阻塞的任务
```

---

## 完整 API / Full API

```python
tracker = TaskTracker()

# 创建
task = tracker.create(
    subject="任务标题",
    description="详细说明",
    blocked_by=["task_xxx"],     # 可选
    metadata={"priority": "high"}, # 可选
)

# 读取
task = tracker.get("task_xxx")     # 返回 Task 或 None

# 更新
tracker.update("task_xxx",
    status=TaskStatus.COMPLETED,    # 更新状态
    subject="新标题",                # 更新标题
    description="新描述",            # 更新描述
    metadata={"key": "value"},      # 合并元数据
    add_blocked_by=["task_yyy"],    # 添加依赖
    add_blocks=["task_zzz"],        # 添加阻塞
)

# 删除（自动清理依赖引用）
tracker.delete("task_xxx")

# 列表
all_tasks = tracker.list()                          # 全部
pending = tracker.list(status=TaskStatus.PENDING)    # 按状态过滤
available = tracker.available()                      # 可执行的（pending + 不被阻塞）
is_blocked = tracker.is_blocked("task_xxx")          # 是否被阻塞
```

---

## 删除时的引用清理 / Cleanup on Delete

删除任务时会自动清理所有依赖引用：

```python
t1 = tracker.create("A")
t2 = tracker.create("B", blocked_by=[t1.id])

print(t2.blocked_by)  # [t1.id]

tracker.delete(t1.id)
print(t2.blocked_by)  # [] — 引用已清理
```
