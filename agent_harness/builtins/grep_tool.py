"""GrepTool — search file contents using regex. Mirrors Claude Code's GrepTool.

Uses Python's re module for regex search (no ripgrep dependency).
Supports output modes, context lines, case-insensitive search, glob filtering.
"""

from __future__ import annotations

import fnmatch
import os
import re
from typing import Any

from pydantic import BaseModel, Field

from agent_harness.tools.base import BaseTool, ToolResult

_DEFAULT_HEAD_LIMIT = 250
_VCS_DIRS = {".git", ".svn", ".hg", ".bzr", ".jj", "__pycache__", "node_modules"}


class GrepInput(BaseModel):
    pattern: str = Field(description="Regular expression pattern to search for")
    path: str | None = Field(
        default=None,
        description="File or directory to search in (defaults to current working directory)",
    )
    glob: str | None = Field(
        default=None,
        description="Glob pattern to filter files, e.g. '*.py', '*.{ts,tsx}'",
    )
    output_mode: str = Field(
        default="files_with_matches",
        description="'content' (matching lines), 'files_with_matches' (file paths only), 'count' (match counts per file)",
    )
    context: int | None = Field(
        default=None, alias="-C",
        description="Lines of context before and after each match (content mode only)",
    )
    before_context: int | None = Field(
        default=None, alias="-B",
        description="Lines before each match (content mode only)",
    )
    after_context: int | None = Field(
        default=None, alias="-A",
        description="Lines after each match (content mode only)",
    )
    case_insensitive: bool = Field(
        default=False, alias="-i",
        description="Case insensitive search",
    )
    head_limit: int = Field(
        default=_DEFAULT_HEAD_LIMIT,
        description="Max results to return (0 for unlimited)",
    )

    model_config = {"populate_by_name": True}


def _should_skip(name: str) -> bool:
    return name in _VCS_DIRS or name.startswith(".")


def _matches_glob(filepath: str, glob_pattern: str | None) -> bool:
    if glob_pattern is None:
        return True
    basename = os.path.basename(filepath)
    # Handle {a,b} patterns by expanding
    if "{" in glob_pattern and "}" in glob_pattern:
        inner = glob_pattern[glob_pattern.index("{") + 1:glob_pattern.index("}")]
        prefix = glob_pattern[:glob_pattern.index("{")]
        suffix = glob_pattern[glob_pattern.index("}") + 1:]
        return any(fnmatch.fnmatch(basename, f"{prefix}{ext}{suffix}") for ext in inner.split(","))
    return fnmatch.fnmatch(basename, glob_pattern)


def _collect_files(root: str, glob_pattern: str | None) -> list[str]:
    """Recursively collect text files, respecting VCS exclusions and glob filter."""
    files: list[str] = []
    if os.path.isfile(root):
        if _matches_glob(root, glob_pattern):
            files.append(root)
        return files

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip VCS/hidden directories
        dirnames[:] = [d for d in dirnames if not _should_skip(d)]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            if _matches_glob(fpath, glob_pattern):
                files.append(fpath)

    return sorted(files)


def _search_file(
    filepath: str,
    regex: re.Pattern,
    output_mode: str,
    before: int,
    after: int,
) -> dict[str, Any] | None:
    """Search a single file. Returns match info or None."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return None

    match_indices: list[int] = []
    for i, line in enumerate(lines):
        if regex.search(line):
            match_indices.append(i)

    if not match_indices:
        return None

    if output_mode == "files_with_matches":
        return {"file": filepath, "matches": len(match_indices)}

    if output_mode == "count":
        return {"file": filepath, "count": len(match_indices)}

    # content mode
    output_lines: list[str] = []
    shown: set[int] = set()

    for idx in match_indices:
        start = max(0, idx - before)
        end = min(len(lines), idx + after + 1)
        for i in range(start, end):
            if i not in shown:
                shown.add(i)
                prefix = f"{i + 1}\t"
                output_lines.append(f"{prefix}{lines[i].rstrip()}")
        if end < len(lines):
            output_lines.append("--")

    return {
        "file": filepath,
        "matches": len(match_indices),
        "content": "\n".join(output_lines),
    }


class GrepToolImpl(BaseTool):
    name = "grep"
    description = (
        "Search file contents using regex patterns. Supports output modes: "
        "'files_with_matches' (default, shows file paths), 'content' (shows "
        "matching lines with context), 'count' (match counts). "
        "Automatically skips .git, node_modules, and hidden directories."
    )
    input_model = GrepInput
    is_read_only = True
    is_concurrency_safe = True

    async def call(self, input: dict[str, Any], context: Any) -> ToolResult:
        parsed = GrepInput.model_validate(input)

        search_path = parsed.path or os.getcwd()
        if not os.path.exists(search_path):
            return ToolResult(content=f"Error: path not found: {search_path}", is_error=True)

        # Compile regex
        flags = re.IGNORECASE if parsed.case_insensitive else 0
        try:
            regex = re.compile(parsed.pattern, flags)
        except re.error as e:
            return ToolResult(content=f"Error: invalid regex pattern: {e}", is_error=True)

        # Context lines
        ctx_before = parsed.context or parsed.before_context or 0
        ctx_after = parsed.context or parsed.after_context or 0

        # Collect files
        files = _collect_files(search_path, parsed.glob)

        # Search
        results: list[dict[str, Any]] = []
        for fpath in files:
            match = _search_file(fpath, regex, parsed.output_mode, ctx_before, ctx_after)
            if match:
                results.append(match)
                if parsed.head_limit > 0 and len(results) >= parsed.head_limit:
                    break

        if not results:
            return ToolResult(content=f"No matches found for pattern '{parsed.pattern}'")

        # Format output
        if parsed.output_mode == "files_with_matches":
            lines = [r["file"] for r in results]
            text = "\n".join(lines)
            text += f"\n\n({len(results)} file(s) matched)"

        elif parsed.output_mode == "count":
            lines = [f"{r['file']}: {r['count']}" for r in results]
            total = sum(r["count"] for r in results)
            text = "\n".join(lines)
            text += f"\n\n(total: {total} matches in {len(results)} files)"

        else:  # content
            parts: list[str] = []
            for r in results:
                parts.append(f"=== {r['file']} ({r['matches']} matches) ===")
                parts.append(r["content"])
                parts.append("")
            text = "\n".join(parts)

        if parsed.head_limit > 0 and len(results) >= parsed.head_limit:
            text += f"\n(results limited to {parsed.head_limit}, set head_limit=0 for all)"

        return ToolResult(content=text)


grep = GrepToolImpl()
