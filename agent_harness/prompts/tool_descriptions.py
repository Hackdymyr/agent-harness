"""Rich tool descriptions — ported from Claude Code's per-tool prompt.ts files.

Each built-in tool gets a comprehensive description that guides the LLM on
when and how to use it, common pitfalls, and best practices. These replace
the 2-4 line descriptions in the default built-in tools.

The enrich_tools() function creates a new ToolRegistry with rich descriptions
while leaving the original registry and tool instances untouched.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_harness.tools.base import BaseTool, ToolRegistry


# ── Rich Descriptions ────────────────────────────────────────────────────────

RICH_DESCRIPTIONS: dict[str, str] = {}

RICH_DESCRIPTIONS["bash"] = """\
Execute a shell command and return its output (stdout + stderr combined).

# Instructions

- Commands run in the user's default shell with a default timeout of 120 seconds (max 600 seconds).
- The working directory persists between commands via the cwd parameter, but shell state (variables, aliases) does not.
- Results are returned as text. Output longer than 200KB is truncated, showing the first and last portions.

# When to Use

Use this tool for:
- System operations: running scripts, package management, process management
- Git commands: status, diff, log, commit, push (see Git Safety below)
- Build and test commands: make, pytest, npm test, cargo build
- Any operation that requires shell execution

Do NOT use this tool when a dedicated tool is available:
- To read files → use read_file (provides line numbers, handles binary detection)
- To write files → use write_file (creates parent dirs, reports line counts)
- To edit files → use edit_file (exact string replacement, safer than sed/awk)
- To search file names → use glob (faster, respects exclusions)
- To search file contents → use grep (structured output modes, context lines)
- To list directories → use list_dir (tree format, size info)

# Command Patterns

- Independent commands that can run in parallel: make separate tool calls
- Sequential commands with dependencies: chain with && (e.g., cd dir && make)
- Commands where earlier failures don't matter: chain with ; (e.g., cmd1 ; cmd2)
- Always quote file paths containing spaces with double quotes
- Prefer absolute paths to avoid working directory confusion

# Git Safety Protocol

When working with git:
- NEVER use --force, --hard, or other destructive flags unless explicitly asked
- NEVER amend commits unless explicitly asked — prefer creating new commits
- NEVER skip hooks with --no-verify
- NEVER force push to main/master
- Prefer staging specific files (git add file1 file2) over git add -A or git add .
- Before destructive operations, consider if there is a safer alternative
- When a pre-commit hook fails, fix the issue and create a NEW commit (do not amend)

# Timeout and Background

- Default timeout: 120 seconds. Specify a longer timeout for slow operations.
- For long-running commands, consider using background execution if available.
- Avoid unnecessary sleep commands — run commands directly or use polling.

# Output Handling

- Exit code 0 = success; non-zero = error (the result will be marked as error)
- Large outputs are automatically truncated to prevent context overflow
- Binary output may not display correctly — redirect to a file if needed\
"""

RICH_DESCRIPTIONS["read_file"] = """\
Read a file from the local filesystem and return its content with line numbers.

# Instructions

- The file_path parameter must be an absolute path, not a relative path.
- By default, reads up to 2000 lines from the beginning of the file.
- You can specify offset (starting line, 0-based) and limit (number of lines) for targeted reads of large files.
- Results are returned with line numbers (like cat -n format), starting at line 1.
- This tool can detect binary files and will warn you instead of showing garbled content.

# When to Use

- ALWAYS read a file before editing it — you need the exact content for edit_file's string matching.
- Use this to understand code before suggesting modifications.
- Use offset/limit to read specific sections of very large files rather than loading the entire file.
- For finding files by name, use glob instead.
- For searching file contents, use grep instead — it's much faster for pattern matching.

# Important Notes

- This tool reads files only, not directories. To list directory contents, use list_dir or glob.
- If the file does not exist, an error is returned.
- Empty files return a warning instead of empty content.\
"""

RICH_DESCRIPTIONS["write_file"] = """\
Write content to a file, creating it if it doesn't exist or overwriting if it does.

# Instructions

- The file_path parameter must be an absolute path, not a relative path.
- Parent directories are automatically created if they don't exist.
- This tool will OVERWRITE the entire file content. There is no append mode.

# When to Use

- Use this to create NEW files.
- For modifying EXISTING files, prefer edit_file — it only changes the specific part you want,
  which is safer and preserves the rest of the file.
- If you must use write_file on an existing file, ALWAYS read_file first to understand the current
  content and avoid accidentally losing data.

# Important Notes

- Do not create documentation files (*.md, README) unless explicitly requested.
- Do not create files unless they are necessary for the task at hand.
- Prefer editing existing files over creating new ones to avoid file bloat.\
"""

RICH_DESCRIPTIONS["edit_file"] = """\
Perform exact string replacements in a file. Finds old_string and replaces it with new_string.

# Instructions

- The file_path parameter must be an absolute path.
- You MUST read_file first before editing — you need the exact text to match against.
- old_string must match EXACTLY, including all whitespace, indentation, and line breaks.
- When reading file content from read_file output, the line number prefix format is: number + tab.
  Everything after the tab is the actual file content. Never include the line number prefix in old_string.
- By default, old_string must appear exactly once in the file. If it appears multiple times, the edit
  will FAIL. Either:
  - Provide more surrounding context to make the match unique, OR
  - Set replace_all=True to replace every occurrence.

# When to Use

- This is the PREFERRED tool for modifying existing files.
- Safer than write_file because it only changes the targeted text.
- Supports multiline replacements — old_string and new_string can span multiple lines.

# Common Pitfalls

- Forgetting to read the file first → old_string won't match
- Wrong indentation (tabs vs spaces, wrong indent level) → match fails
- Not enough context in old_string → multiple matches, edit fails
- Including line numbers from read_file output in old_string → match fails\
"""

RICH_DESCRIPTIONS["glob"] = """\
Find files matching a glob pattern. Returns matching file paths sorted by modification time (newest first).

# Instructions

- Supports standard glob patterns:
  - `**/*.py` — all Python files recursively
  - `src/**/*.ts` — TypeScript files under src/
  - `*.{js,jsx}` — JavaScript and JSX files in current directory
  - `?` — matches a single character
- Automatically skips .git, node_modules, __pycache__, .svn directories.
- Results are limited to 200 matches; a truncation notice is shown if exceeded.

# When to Use

- Use this to find files by name or extension before reading them.
- Use this when you need to understand the project structure.
- For searching file CONTENTS (not names), use grep instead.
- When you need a broader codebase exploration, combine glob with read_file.\
"""

RICH_DESCRIPTIONS["grep"] = """\
Search file contents using regex patterns. Built on Python's re module.

# Instructions

- pattern: A regular expression (Python re syntax). For literal special characters, escape them
  (e.g., `\\.` to match a period, `\\{\\}` to match braces).
- Output modes:
  - "files_with_matches" (default): Returns only file paths containing matches.
  - "content": Returns matching lines with optional context lines (-A/-B/-C).
  - "count": Returns match counts per file.
- Context lines (only with output_mode="content"):
  - -A (after): Number of lines to show after each match
  - -B (before): Number of lines to show before each match
  - -C (context): Lines before AND after each match
- Case-insensitive search: Set the -i flag.
- File filtering: Use the glob parameter (e.g., "*.py") to restrict which files are searched.
- Default result limit: 250 matches. Use head_limit to override.

# When to Use

- Use this for searching code: finding function definitions, imports, string patterns, TODO comments.
- Use output_mode="files_with_matches" first to find relevant files, then read_file for details.
- For finding files by name (not content), use glob instead.

# Pattern Tips

- Function definitions: `def my_function`, `class MyClass`, `function myFunc`
- Import statements: `from module import`, `import.*module`
- TODO/FIXME: `(TODO|FIXME|HACK|XXX)`
- Multiline patterns are NOT supported — each line is matched independently.\
"""

RICH_DESCRIPTIONS["list_dir"] = """\
List directory contents in a tree format showing files with sizes and directories.

# Instructions

- Displays a visual tree structure with ASCII art (├──, └──).
- Files show their size (B, KB, MB, GB).
- Directories are listed without size.
- Automatically skips .git, node_modules, and hidden entries (dotfiles).
- Use recursive=True for a full tree view, with max_depth to control depth.

# When to Use

- Use this to get an overview of a directory's structure.
- For finding specific files by pattern, use glob instead.
- For searching file contents, use grep instead.
- Useful as a first step when exploring an unfamiliar project.\
"""

RICH_DESCRIPTIONS["spawn_agent"] = """\
Spawn a sub-agent to handle a subtask autonomously.

The sub-agent runs with its own conversation context (fresh message history) and returns
its final response as a string. Use this for parallel work or specialized tasks that
benefit from isolation.

# When to Use

- Complex tasks that can be parallelized: spawn multiple sub-agents for independent work
- Specialized exploration: give a sub-agent read-only tools to research a question
- Isolated operations: tasks that shouldn't pollute the main conversation history
- Long-running subtasks: delegate work that would otherwise consume many turns

# When NOT to Use

- Simple, quick tasks that you can do directly — the overhead of spawning isn't worth it
- Tasks that need the full conversation history — sub-agents start fresh
- When you need to read a specific file — just use read_file directly

# How It Works

- Each sub-agent gets a fresh message history (no access to parent conversation)
- You can scope which tools the sub-agent can use via allowed_tools
- The sub-agent shares the same LLM client and permission settings as the parent
- Use max_turns to prevent runaway agents (default from parent context)
- The sub-agent's final text response is returned to you

# Writing Good Prompts for Sub-Agents

Brief the sub-agent like a colleague who just walked into the room:
- Explain what you're trying to accomplish and why
- Describe what you've already learned or ruled out
- Give enough context for the sub-agent to make judgment calls
- If you need a short response, say so ("report in under 200 words")
- Include file paths and specific details — don't make the sub-agent search for things you already know\
"""


# ── Public API ────────────────────────────────────────────────────────────────

def get_rich_description(tool_name: str) -> str | None:
    """Look up the rich description for a built-in tool by name."""
    return RICH_DESCRIPTIONS.get(tool_name)


def enrich_tools(registry: "ToolRegistry") -> "ToolRegistry":
    """Create a new ToolRegistry with rich descriptions for known built-in tools.

    Unknown tools are passed through with their original descriptions.
    The original registry is NOT modified.

    Args:
        registry: The original ToolRegistry.

    Returns:
        A new ToolRegistry with enriched tool descriptions.
    """
    from agent_harness.tools.base import ToolRegistry

    enriched_tools: list[BaseTool] = []
    for tool in registry.list():
        rich_desc = RICH_DESCRIPTIONS.get(tool.name)
        if rich_desc:
            tool_copy = copy.copy(tool)
            tool_copy.description = rich_desc
            enriched_tools.append(tool_copy)
        else:
            enriched_tools.append(tool)

    return ToolRegistry(enriched_tools)
