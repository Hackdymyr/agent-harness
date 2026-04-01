"""FileEditTool — exact string replacement in files. Mirrors Claude Code's FileEditTool.

Key behavior: old_string must be unique in the file unless replace_all=True.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from agent_harness.tools.base import BaseTool, ToolResult


class EditFileInput(BaseModel):
    file_path: str = Field(description="The absolute path to the file to modify")
    old_string: str = Field(description="The exact text to find and replace")
    new_string: str = Field(description="The replacement text (must differ from old_string)")
    replace_all: bool = Field(
        default=False,
        description="Replace all occurrences of old_string (default: False, requires unique match)",
    )


class EditFileTool(BaseTool):
    name = "edit_file"
    description = (
        "Perform exact string replacements in a file. The old_string must match "
        "exactly (including whitespace and indentation). By default, old_string "
        "must be unique in the file — set replace_all=True to replace every occurrence."
    )
    input_model = EditFileInput
    is_read_only = False
    is_concurrency_safe = False

    async def call(self, input: dict[str, Any], context: Any) -> ToolResult:
        parsed = EditFileInput.model_validate(input)
        path = parsed.file_path

        if not os.path.isabs(path):
            return ToolResult(content=f"Error: path must be absolute, got '{path}'", is_error=True)

        if not os.path.exists(path):
            return ToolResult(content=f"Error: file not found: {path}", is_error=True)

        if parsed.old_string == parsed.new_string:
            return ToolResult(content="Error: old_string and new_string are identical", is_error=True)

        # Read current content
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            return ToolResult(content=f"Error reading file: {e}", is_error=True)

        # Check occurrences
        count = content.count(parsed.old_string)

        if count == 0:
            # Try to help: show nearby content
            return ToolResult(
                content=f"Error: old_string not found in {path}. Make sure the string matches exactly, including whitespace and indentation.",
                is_error=True,
            )

        if count > 1 and not parsed.replace_all:
            return ToolResult(
                content=(
                    f"Error: old_string appears {count} times in {path}. "
                    "Provide more surrounding context to make it unique, or set replace_all=True."
                ),
                is_error=True,
            )

        # Perform replacement
        if parsed.replace_all:
            new_content = content.replace(parsed.old_string, parsed.new_string)
        else:
            new_content = content.replace(parsed.old_string, parsed.new_string, 1)

        # Write back
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_content)
        except OSError as e:
            return ToolResult(content=f"Error writing file: {e}", is_error=True)

        replacements = count if parsed.replace_all else 1
        return ToolResult(content=f"Edited {path}: replaced {replacements} occurrence(s)")


edit_file = EditFileTool()
