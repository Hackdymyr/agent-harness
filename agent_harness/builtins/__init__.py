"""Built-in tools — ready-to-use tools inspired by Claude Code's tool set.

Usage:
    from agent_harness.builtins import read_file, write_file, edit_file, bash, grep, glob_tool
    from agent_harness import ToolRegistry

    registry = ToolRegistry([read_file, write_file, edit_file, bash, grep, glob_tool])
"""

from agent_harness.builtins.file_read import read_file
from agent_harness.builtins.file_write import write_file
from agent_harness.builtins.file_edit import edit_file
from agent_harness.builtins.bash_tool import bash
from agent_harness.builtins.grep_tool import grep
from agent_harness.builtins.glob_tool import glob_tool
from agent_harness.builtins.list_dir import list_dir

ALL_TOOLS = [read_file, write_file, edit_file, bash, grep, glob_tool, list_dir]
