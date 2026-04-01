"""ListDirectoryTool — list directory contents with metadata.

Claude Code doesn't have a dedicated list_dir tool (it uses bash ls),
but this is a useful addition for a Python library.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from agent_harness.tools.base import BaseTool, ToolResult

_SKIP_DIRS = {".git", ".svn", ".hg", "__pycache__", "node_modules"}


class ListDirInput(BaseModel):
    path: str = Field(description="The directory path to list")
    recursive: bool = Field(
        default=False,
        description="List contents recursively (default: False, single level only)",
    )
    max_depth: int = Field(
        default=3,
        description="Maximum recursion depth when recursive=True",
    )


def _format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _list_tree(dirpath: str, prefix: str, depth: int, max_depth: int) -> list[str]:
    """Build a tree-style listing."""
    if depth > max_depth:
        return [f"{prefix}..."]

    try:
        entries = sorted(os.listdir(dirpath))
    except PermissionError:
        return [f"{prefix}(permission denied)"]

    lines: list[str] = []
    dirs = []
    files = []

    for name in entries:
        if name in _SKIP_DIRS or name.startswith("."):
            continue
        full = os.path.join(dirpath, name)
        if os.path.isdir(full):
            dirs.append(name)
        else:
            files.append(name)

    # Directories first, then files
    all_items = [(d, True) for d in dirs] + [(f, False) for f in files]

    for i, (name, is_dir) in enumerate(all_items):
        is_last = i == len(all_items) - 1
        connector = "└── " if is_last else "├── "
        full = os.path.join(dirpath, name)

        if is_dir:
            lines.append(f"{prefix}{connector}{name}/")
            if depth < max_depth:
                extension = "    " if is_last else "│   "
                lines.extend(_list_tree(full, prefix + extension, depth + 1, max_depth))
        else:
            try:
                size = _format_size(os.path.getsize(full))
            except OSError:
                size = "?"
            lines.append(f"{prefix}{connector}{name} ({size})")

    return lines


class ListDirTool(BaseTool):
    name = "list_dir"
    description = (
        "List directory contents in a tree format. Shows files with sizes "
        "and directories. Skips .git, node_modules, and hidden entries. "
        "Use recursive=True for a full tree view."
    )
    input_model = ListDirInput
    is_read_only = True
    is_concurrency_safe = True

    async def call(self, input: dict[str, Any], context: Any) -> ToolResult:
        parsed = ListDirInput.model_validate(input)
        path = parsed.path

        if not os.path.exists(path):
            return ToolResult(content=f"Error: path not found: {path}", is_error=True)

        if not os.path.isdir(path):
            return ToolResult(content=f"Error: '{path}' is not a directory", is_error=True)

        if parsed.recursive:
            lines = [f"{path}/"]
            lines.extend(_list_tree(path, "", 1, parsed.max_depth))
        else:
            lines = [f"{path}/"]
            try:
                entries = sorted(os.listdir(path))
            except PermissionError:
                return ToolResult(content=f"Error: permission denied: {path}", is_error=True)

            for name in entries:
                if name in _SKIP_DIRS or name.startswith("."):
                    continue
                full = os.path.join(path, name)
                if os.path.isdir(full):
                    lines.append(f"  {name}/")
                else:
                    try:
                        size = _format_size(os.path.getsize(full))
                    except OSError:
                        size = "?"
                    lines.append(f"  {name} ({size})")

        return ToolResult(content="\n".join(lines))


list_dir = ListDirTool()
