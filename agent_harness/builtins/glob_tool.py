"""GlobTool — find files by pattern. Mirrors Claude Code's GlobTool.

Uses Python's pathlib/glob (no ripgrep dependency).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent_harness.tools.base import BaseTool, ToolResult

_MAX_RESULTS = 200
_SKIP_DIRS = {".git", ".svn", ".hg", "__pycache__", "node_modules", ".tox", ".venv", "venv"}


class GlobInput(BaseModel):
    pattern: str = Field(description="Glob pattern to match, e.g. '**/*.py', 'src/**/*.ts'")
    path: str | None = Field(
        default=None,
        description="Directory to search in (defaults to current working directory)",
    )


class GlobToolImpl(BaseTool):
    name = "glob"
    description = (
        "Find files matching a glob pattern. Supports '**' for recursive matching, "
        "'*' for single-level wildcards, '?' for single character. "
        "Returns matching file paths sorted by modification time."
    )
    input_model = GlobInput
    is_read_only = True
    is_concurrency_safe = True

    async def call(self, input: dict[str, Any], context: Any) -> ToolResult:
        parsed = GlobInput.model_validate(input)
        search_dir = parsed.path or os.getcwd()

        if not os.path.isdir(search_dir):
            return ToolResult(content=f"Error: directory not found: {search_dir}", is_error=True)

        base = Path(search_dir)

        try:
            raw_matches = list(base.glob(parsed.pattern))
        except Exception as e:
            return ToolResult(content=f"Error: invalid glob pattern: {e}", is_error=True)

        # Filter out VCS/hidden directories and files within them
        matches: list[Path] = []
        for m in raw_matches:
            parts = m.relative_to(base).parts
            if any(p in _SKIP_DIRS for p in parts):
                continue
            if m.is_file():
                matches.append(m)

        # Sort by modification time (newest first)
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        truncated = len(matches) > _MAX_RESULTS
        matches = matches[:_MAX_RESULTS]

        if not matches:
            return ToolResult(content=f"No files found matching pattern '{parsed.pattern}' in {search_dir}")

        lines = [str(m) for m in matches]
        text = "\n".join(lines)
        text += f"\n\n({len(matches)} file(s) found"
        if truncated:
            text += f", results truncated to {_MAX_RESULTS}"
        text += ")"

        return ToolResult(content=text)


glob_tool = GlobToolImpl()
