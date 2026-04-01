"""BashTool — execute shell commands. Mirrors Claude Code's BashTool.

Captures stdout + stderr, supports timeout, handles large output.
"""

from __future__ import annotations

import asyncio
import os
import platform
from typing import Any

from pydantic import BaseModel, Field

from agent_harness.tools.base import BaseTool, ToolResult

_IS_WINDOWS = platform.system() == "Windows"
_DEFAULT_TIMEOUT = 120  # seconds
_MAX_OUTPUT_SIZE = 200_000  # characters


class BashInput(BaseModel):
    command: str = Field(description="The shell command to execute")
    timeout: int | None = Field(
        default=None,
        description=f"Timeout in seconds (default: {_DEFAULT_TIMEOUT}, max: 600)",
    )
    description: str | None = Field(
        default=None,
        description="Short description of what this command does",
    )


class BashToolImpl(BaseTool):
    name = "bash"
    description = (
        "Execute a shell command and return its output (stdout + stderr). "
        "Commands run in the user's default shell. Use this for system operations, "
        "running scripts, git commands, package management, etc."
    )
    input_model = BashInput
    is_read_only = False
    is_concurrency_safe = False

    async def call(self, input: dict[str, Any], context: Any) -> ToolResult:
        parsed = BashInput.model_validate(input)
        command = parsed.command
        timeout = min(parsed.timeout or _DEFAULT_TIMEOUT, 600)

        if not command.strip():
            return ToolResult(content="Error: empty command", is_error=True)

        # Choose shell
        if _IS_WINDOWS:
            shell_cmd = ["cmd", "/c", command]
        else:
            shell = os.environ.get("SHELL", "/bin/bash")
            shell_cmd = [shell, "-c", command]

        try:
            proc = await asyncio.create_subprocess_exec(
                *shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
                cwd=getattr(context, "cwd", None) if context else None,
            )

            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    content=f"Error: command timed out after {timeout}s",
                    is_error=True,
                )

        except FileNotFoundError:
            return ToolResult(
                content=f"Error: shell not found for command execution",
                is_error=True,
            )
        except OSError as e:
            return ToolResult(content=f"Error: {e}", is_error=True)

        # Decode output
        output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""

        # Truncate very large output
        truncated = False
        if len(output) > _MAX_OUTPUT_SIZE:
            truncated = True
            # Keep first and last parts
            half = _MAX_OUTPUT_SIZE // 2
            output = (
                output[:half]
                + f"\n\n... ({len(output) - _MAX_OUTPUT_SIZE} characters truncated) ...\n\n"
                + output[-half:]
            )

        exit_code = proc.returncode or 0

        # Format result
        if not output.strip():
            output = "(no output)"

        result_text = output
        if exit_code != 0:
            result_text = f"Exit code: {exit_code}\n{output}"
        if truncated:
            result_text = f"(output truncated to {_MAX_OUTPUT_SIZE} chars)\n{result_text}"

        return ToolResult(
            content=result_text,
            is_error=exit_code != 0,
        )


bash = BashToolImpl()
