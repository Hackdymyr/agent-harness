"""Tool orchestration — mirrors Claude Code's toolOrchestration.ts.

Core pattern: partition tool calls into concurrent (read-only) and serial (mutating)
batches, then execute each batch appropriately.
"""

from __future__ import annotations

import asyncio
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agent_harness.types import ToolCall, ToolResultContent

if TYPE_CHECKING:
    from agent_harness.tools.base import BaseTool, ToolRegistry, ToolResult
    from agent_harness.tools.permissions import PermissionChecker
    from agent_harness.agent.context import AgentContext


@dataclass
class _Batch:
    is_concurrent: bool
    tool_calls: list[ToolCall] = field(default_factory=list)


def _partition_tool_calls(
    tool_calls: list[ToolCall], registry: "ToolRegistry"
) -> list[_Batch]:
    """Partition tool calls into concurrent vs serial batches.

    Mirrors partitionToolCalls() from toolOrchestration.ts:
    - Consecutive read-only + concurrency-safe tools are batched together
    - Everything else runs in its own serial batch
    """
    batches: list[_Batch] = []

    for tc in tool_calls:
        tool = registry.get(tc.name)
        is_safe = (
            tool is not None and tool.is_concurrency_safe and tool.is_read_only
        )

        if is_safe and batches and batches[-1].is_concurrent:
            batches[-1].tool_calls.append(tc)
        else:
            batches.append(_Batch(is_concurrent=is_safe, tool_calls=[tc]))

    return batches


async def _execute_single(
    tc: ToolCall,
    registry: "ToolRegistry",
    context: "AgentContext",
    permission_checker: "PermissionChecker",
) -> ToolResultContent:
    """Execute a single tool call with validation + permissions + error handling.

    Mirrors checkPermissionsAndCallTool() from toolExecution.ts:
    1. Find tool in registry
    2. Validate input with Pydantic
    3. Check permissions
    4. Call the tool
    5. Wrap result in ToolResultContent
    """
    tool = registry.get(tc.name)

    # Tool not found
    if tool is None:
        available = ", ".join(registry.names())
        return ToolResultContent(
            tool_use_id=tc.id,
            content=f"Error: Tool '{tc.name}' not found. Available tools: {available}",
            is_error=True,
        )

    # Validate input
    is_valid, _, error_msg = tool.validate_input(tc.input)
    if not is_valid:
        return ToolResultContent(
            tool_use_id=tc.id,
            content=f"Input validation error for '{tc.name}': {error_msg}",
            is_error=True,
        )

    # Check permissions
    permitted = await permission_checker.check(tool, tc.input, context)
    if not permitted:
        return ToolResultContent(
            tool_use_id=tc.id,
            content=f"Permission denied for tool '{tc.name}'.",
            is_error=True,
        )

    # Tool-specific permission check
    tool_permitted = await tool.check_permission(tc.input, context)
    if not tool_permitted:
        return ToolResultContent(
            tool_use_id=tc.id,
            content=f"Tool '{tc.name}' denied this operation.",
            is_error=True,
        )

    # Execute
    try:
        result: ToolResult = await tool.call(tc.input, context)

        # Apply context updates if any
        if result.context_updates and context.metadata is not None:
            context.metadata.update(result.context_updates)

        return ToolResultContent(
            tool_use_id=tc.id,
            content=result.content,
            is_error=result.is_error,
        )
    except Exception as e:
        return ToolResultContent(
            tool_use_id=tc.id,
            content=f"Error executing '{tc.name}': {e}\n{traceback.format_exc()}",
            is_error=True,
        )


async def execute_tool_calls(
    tool_calls: list[ToolCall],
    registry: "ToolRegistry",
    context: "AgentContext",
    permission_checker: "PermissionChecker",
    max_concurrency: int = 10,
) -> list[ToolResultContent]:
    """Execute tool calls respecting concurrency partitioning.

    Mirrors runTools() from toolOrchestration.ts:
    - Read-only + concurrency-safe tools run in parallel (bounded by semaphore)
    - Mutating tools run one at a time
    - Results are returned in the same order as input tool_calls
    """
    if not tool_calls:
        return []

    batches = _partition_tool_calls(tool_calls, registry)
    results: list[ToolResultContent] = []

    for batch in batches:
        if batch.is_concurrent and len(batch.tool_calls) > 1:
            sem = asyncio.Semaphore(max_concurrency)

            async def _bounded(tc: ToolCall) -> ToolResultContent:
                async with sem:
                    return await _execute_single(tc, registry, context, permission_checker)

            batch_results = await asyncio.gather(
                *[_bounded(tc) for tc in batch.tool_calls]
            )
            results.extend(batch_results)
        else:
            for tc in batch.tool_calls:
                result = await _execute_single(tc, registry, context, permission_checker)
                results.append(result)

    return results
