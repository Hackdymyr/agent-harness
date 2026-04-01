"""Task tracker — in-memory task list with dependency tracking.

Mirrors Claude Code's TaskCreate/TaskUpdate/TaskList tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class Task:
    id: str
    subject: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskTracker:
    """In-memory task list with dependency tracking.

    Usage:
        tracker = TaskTracker()
        t1 = tracker.create("Implement auth", "Add JWT authentication")
        t2 = tracker.create("Write tests", blocked_by=[t1.id])
        tracker.update(t1.id, status=TaskStatus.IN_PROGRESS)
        tracker.update(t1.id, status=TaskStatus.COMPLETED)
        # Now t2 is unblocked
    """

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def create(
        self,
        subject: str,
        description: str = "",
        blocked_by: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        task_id = f"task_{uuid4().hex[:8]}"
        task = Task(
            id=task_id,
            subject=subject,
            description=description,
            blocked_by=list(blocked_by) if blocked_by else [],
            metadata=dict(metadata) if metadata else {},
        )

        # Update reverse dependency: add this task to blockers' blocks list
        for blocker_id in task.blocked_by:
            blocker = self._tasks.get(blocker_id)
            if blocker and task_id not in blocker.blocks:
                blocker.blocks.append(task_id)

        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs: Any) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task '{task_id}' not found")

        for key, value in kwargs.items():
            if key == "status":
                task.status = TaskStatus(value) if isinstance(value, str) else value
            elif key == "subject":
                task.subject = value
            elif key == "description":
                task.description = value
            elif key == "metadata":
                task.metadata.update(value)
            elif key == "add_blocked_by":
                for bid in value:
                    if bid not in task.blocked_by:
                        task.blocked_by.append(bid)
                    blocker = self._tasks.get(bid)
                    if blocker and task_id not in blocker.blocks:
                        blocker.blocks.append(task_id)
            elif key == "add_blocks":
                for bid in value:
                    if bid not in task.blocks:
                        task.blocks.append(bid)
                    blocked = self._tasks.get(bid)
                    if blocked and task_id not in blocked.blocked_by:
                        blocked.blocked_by.append(task_id)

        return task

    def delete(self, task_id: str) -> None:
        task = self._tasks.pop(task_id, None)
        if task is None:
            return
        # Clean up dependency references
        for other in self._tasks.values():
            if task_id in other.blocks:
                other.blocks.remove(task_id)
            if task_id in other.blocked_by:
                other.blocked_by.remove(task_id)

    def list(self, status: TaskStatus | None = None) -> list[Task]:
        tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def is_blocked(self, task_id: str) -> bool:
        """Check if all blockers are completed."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        for blocker_id in task.blocked_by:
            blocker = self._tasks.get(blocker_id)
            if blocker and blocker.status != TaskStatus.COMPLETED:
                return True
        return False

    def available(self) -> list[Task]:
        """Return tasks that are pending and not blocked."""
        return [
            t
            for t in self._tasks.values()
            if t.status == TaskStatus.PENDING and not self.is_blocked(t.id)
        ]
