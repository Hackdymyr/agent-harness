"""Compaction prompt templates.

Mirrors Claude Code's src/services/compact/prompt.ts — defines the
9-section summary format that the LLM uses when compressing conversations.
"""

from __future__ import annotations

import re

COMPACT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant tasked with summarizing conversations."
)

BASE_COMPACT_PROMPT = """\
Your task is to create a detailed summary of the conversation so far. This summary will replace the conversation history, so it must be comprehensive and capture all important information.

Please create a summary that includes:

1. **Primary Request and Intent**: Describe all of the user's explicit requests and the intent behind them in detail. Include every task, question, or goal the user has mentioned.

2. **Key Technical Concepts**: List all technologies, frameworks, libraries, and technical concepts discussed. Include version numbers, configuration details, and technical decisions made.

3. **Files and Code Sections**: Reference specific files that were read, created, or modified. For code that was written or modified, include the COMPLETE code snippets — not just descriptions. For files that were only read or referenced, describe their relevant content and structure.

4. **Errors and Fixes**: Document all errors encountered, their root causes, and the solutions applied. Include error messages and stack traces.

5. **Problem Solving**: Describe the overall problem-solving approach, problems solved so far, and any ongoing troubleshooting efforts.

6. **All User Messages**: Reproduce the content of all user messages (non-tool-result) that appeared in the conversation, but not the assistant messages. Preserve the user's exact wording for important requests.

7. **Pending Tasks**: List any tasks the user has explicitly requested that haven't been completed yet.

8. **Current Work**: Describe precisely what was being worked on immediately before this summary was requested. Include file paths, function names, and the exact state of any in-progress changes.

9. **Optional Next Step**: If there is a clear next step that was about to be taken, describe it briefly.

Format your response as:

<analysis>
[Your internal analysis and reasoning about what to include — this section will be stripped]
</analysis>

<summary>
[The actual summary content organized by the sections above]
</summary>"""


NO_TOOLS_PREAMBLE = """\
CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.
Your entire response must be plain text: an <analysis> block followed by a <summary> block.

"""

NO_TOOLS_TRAILER = """

REMINDER: Do NOT call any tools. Respond with plain text only — an <analysis> block and a <summary> block."""


def get_compact_prompt(custom_instructions: str | None = None) -> str:
    """Assemble the full compaction prompt.

    Mirrors Claude Code's getCompactPrompt().
    """
    prompt = NO_TOOLS_PREAMBLE + BASE_COMPACT_PROMPT
    if custom_instructions and custom_instructions.strip():
        prompt += f"\n\nAdditional Instructions:\n{custom_instructions}"
    prompt += NO_TOOLS_TRAILER
    return prompt


def format_compact_summary(raw: str) -> str:
    """Parse and format the LLM's compaction output.

    Strips the <analysis> drafting section and extracts the <summary>.
    Mirrors Claude Code's formatCompactSummary().
    """
    result = raw

    # Strip <analysis> block (internal reasoning scratchpad)
    result = re.sub(r"<analysis>[\s\S]*?</analysis>", "", result)

    # Extract and format <summary> block
    summary_match = re.search(r"<summary>([\s\S]*?)</summary>", result)
    if summary_match:
        content = summary_match.group(1).strip()
        result = re.sub(
            r"<summary>[\s\S]*?</summary>",
            f"Summary:\n{content}",
            result,
        )

    # Clean up extra whitespace
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
