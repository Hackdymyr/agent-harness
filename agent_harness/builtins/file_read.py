"""FileReadTool — read file contents with optional offset/limit and line numbers.

Mirrors Claude Code's FileReadTool: adds line numbers, supports offset/limit
for large files, handles text and binary detection.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from agent_harness.tools.base import BaseTool, ToolResult


class ReadFileInput(BaseModel):
    file_path: str = Field(description="The absolute path to the file to read")
    offset: int | None = Field(
        default=None,
        description="The line number to start reading from (0-indexed). Only provide if the file is too large to read at once",
    )
    limit: int | None = Field(
        default=None,
        description="The number of lines to read. Only provide if the file is too large to read at once",
    )


def _add_line_numbers(text: str, start_line: int = 1) -> str:
    """Add line numbers in 'N\\t' format (like cat -n)."""
    lines = text.split("\n")
    numbered = []
    for i, line in enumerate(lines):
        numbered.append(f"{start_line + i}\t{line}")
    return "\n".join(numbered)


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "Read a file from the local filesystem. Returns the file content with "
        "line numbers. You can optionally specify offset and limit for large files."
    )
    input_model = ReadFileInput
    is_read_only = True
    is_concurrency_safe = True

    async def call(self, input: dict[str, Any], context: Any) -> ToolResult:
        parsed = ReadFileInput.model_validate(input)
        path = parsed.file_path

        if not os.path.isabs(path):
            return ToolResult(content=f"Error: path must be absolute, got '{path}'", is_error=True)

        if not os.path.exists(path):
            return ToolResult(content=f"Error: file not found: {path}", is_error=True)

        if os.path.isdir(path):
            return ToolResult(
                content=f"Error: '{path}' is a directory, not a file. Use list_dir or glob to explore directories.",
                is_error=True,
            )

        # Check file size (warn if > 1MB)
        try:
            size = os.path.getsize(path)
        except OSError as e:
            return ToolResult(content=f"Error: {e}", is_error=True)

        # Try to detect binary files
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
                if b"\x00" in chunk:
                    return ToolResult(
                        content=f"Error: '{path}' appears to be a binary file ({size} bytes). Cannot display as text.",
                        is_error=True,
                    )
        except OSError as e:
            return ToolResult(content=f"Error reading file: {e}", is_error=True)

        # Read text file
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except OSError as e:
            return ToolResult(content=f"Error reading file: {e}", is_error=True)

        total_lines = len(all_lines)

        # Apply offset/limit
        offset = parsed.offset or 0
        limit = parsed.limit

        if offset > 0:
            all_lines = all_lines[offset:]

        if limit is not None and limit > 0:
            all_lines = all_lines[:limit]

        content = "".join(all_lines)

        # Remove trailing newline for clean output
        if content.endswith("\n"):
            content = content[:-1]

        # Add line numbers
        start_line = (offset or 0) + 1
        numbered = _add_line_numbers(content, start_line)

        # Add metadata header for large files
        actual_lines = len(content.split("\n")) if content else 0
        if total_lines > actual_lines:
            header = f"(showing lines {start_line}-{start_line + actual_lines - 1} of {total_lines} total)\n"
            numbered = header + numbered

        return ToolResult(content=numbered)


read_file = ReadFileTool()
