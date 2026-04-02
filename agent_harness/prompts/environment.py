"""Runtime environment detection for system prompt injection.

Mirrors Claude Code's computeSimpleEnvInfo() — detects platform, shell,
Python version, git status, and working directory to give the LLM context
about the execution environment.
"""

from __future__ import annotations

import datetime
import os
import platform
import subprocess
import sys

from agent_harness.prompts.sections import PromptSection, SectionPriority


def compute_environment_info(
    cwd: str | None = None,
    include_git: bool = True,
) -> PromptSection:
    """Detect runtime environment and return as a prompt section.

    Args:
        cwd: Working directory to report. Defaults to os.getcwd().
        include_git: Whether to detect git branch and status.

    Returns:
        PromptSection with priority=APPEND and cacheable=False.
    """
    lines: list[str] = ["# Environment"]

    # Platform
    system = platform.system()
    release = platform.release()
    machine = platform.machine()
    lines.append(f"- Platform: {system} {release} ({sys.platform}, {machine})")

    # Shell
    if sys.platform == "win32":
        shell = os.environ.get("SHELL", os.environ.get("COMSPEC", "cmd.exe"))
        lines.append(f"- Shell: {shell}")
        if "bash" in shell.lower() or "git" in shell.lower():
            lines.append("  (Use Unix shell syntax — forward slashes, /dev/null)")
    else:
        shell = os.environ.get("SHELL", "/bin/sh")
        lines.append(f"- Shell: {shell}")

    # Python
    lines.append(f"- Python: {sys.version.split()[0]}")

    # Working directory
    working_dir = cwd or os.getcwd()
    lines.append(f"- Working directory: {working_dir}")

    # Git info
    if include_git:
        git_info = _detect_git(working_dir)
        if git_info:
            lines.append(f"- Git: {git_info}")

    # Date
    lines.append(f"- Date: {datetime.date.today().isoformat()}")

    return PromptSection(
        name="environment_info",
        content="\n".join(lines),
        priority=SectionPriority.APPEND,
        cacheable=False,
    )


def _detect_git(cwd: str) -> str | None:
    """Detect git branch and working tree status."""
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if branch.returncode != 0:
            return None
        branch_name = branch.stdout.strip() or "detached HEAD"

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if status.returncode != 0:
            return f"branch {branch_name}"

        status_lines = [l for l in status.stdout.strip().split("\n") if l.strip()]
        if not status_lines:
            return f"branch {branch_name}, clean working tree"
        else:
            return f"branch {branch_name}, {len(status_lines)} changed file(s)"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
