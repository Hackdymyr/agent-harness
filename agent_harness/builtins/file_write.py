"""FileWriteTool — write/create files. Mirrors Claude Code's FileWriteTool."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from agent_harness.tools.base import BaseTool, ToolResult


class WriteFileInput(BaseModel):
    file_path: str = Field(description="The absolute path to the file to write")
    content: str = Field(description="The content to write to the file")


class WriteFileTool(BaseTool):
    name = "write_file"
    description = (
        "Write content to a file, creating it if it doesn't exist or "
        "overwriting if it does. Use this for creating new files or "
        "completely rewriting existing ones. For partial edits, prefer edit_file."
    )
    input_model = WriteFileInput
    is_read_only = False
    is_concurrency_safe = False

    async def call(self, input: dict[str, Any], context: Any) -> ToolResult:
        parsed = WriteFileInput.model_validate(input)
        path = parsed.file_path

        if not os.path.isabs(path):
            return ToolResult(content=f"Error: path must be absolute, got '{path}'", is_error=True)

        # Create parent directories if needed
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError as e:
                return ToolResult(content=f"Error creating directory: {e}", is_error=True)

        is_new = not os.path.exists(path)

        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(parsed.content)
        except OSError as e:
            return ToolResult(content=f"Error writing file: {e}", is_error=True)

        lines = parsed.content.count("\n") + (1 if parsed.content else 0)
        action = "Created" if is_new else "Updated"
        return ToolResult(content=f"{action} {path} ({lines} lines)")


write_file = WriteFileTool()
