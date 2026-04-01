"""Tool system — mirrors Claude Code's Tool.ts + buildTool pattern."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Awaitable, TYPE_CHECKING

from pydantic import BaseModel, Field

from agent_harness.types import ToolDefinition

if TYPE_CHECKING:
    from agent_harness.agent.context import AgentContext


class ToolResult(BaseModel):
    """What a tool.call() returns."""

    content: str
    is_error: bool = False
    context_updates: dict[str, Any] | None = None


class BaseTool:
    """Base class for all tools. Mirrors Claude Code's Tool type.

    Subclass this or use the @tool decorator to define tools.
    """

    name: str = ""
    description: str = ""
    input_model: type[BaseModel] = BaseModel
    is_read_only: bool = False
    is_concurrency_safe: bool = False

    def to_definition(self) -> ToolDefinition:
        """Convert to JSON Schema for LLM API calls."""
        schema = self.input_model.model_json_schema()
        # Remove Pydantic metadata that LLM APIs don't need
        schema.pop("title", None)
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=schema,
        )

    async def call(self, input: dict[str, Any], context: AgentContext) -> ToolResult:
        """Execute the tool. Override in subclasses."""
        raise NotImplementedError(f"Tool '{self.name}' has no call() implementation")

    async def check_permission(self, input: dict[str, Any], context: AgentContext) -> bool:
        """Tool-specific permission check. Default: allow."""
        return True

    def validate_input(self, raw_input: dict[str, Any]) -> tuple[bool, Any, str]:
        """Validate input against Pydantic model.

        Returns (is_valid, parsed_model_or_None, error_message).
        """
        try:
            parsed = self.input_model.model_validate(raw_input)
            return True, parsed, ""
        except Exception as e:
            return False, None, str(e)


class _FunctionTool(BaseTool):
    """Tool created from a decorated function."""

    def __init__(
        self,
        func: Callable[..., Awaitable[ToolResult]],
        name: str,
        description: str,
        input_model: type[BaseModel],
        is_read_only: bool,
        is_concurrency_safe: bool,
    ):
        self.name = name
        self.description = description
        self.input_model = input_model
        self.is_read_only = is_read_only
        self.is_concurrency_safe = is_concurrency_safe
        self._func = func

    async def call(self, input: dict[str, Any], context: AgentContext) -> ToolResult:
        parsed = self.input_model.model_validate(input)
        sig = inspect.signature(self._func)
        params = list(sig.parameters.keys())

        if len(params) >= 2:
            result = self._func(parsed, context)
        else:
            result = self._func(parsed)

        if inspect.isawaitable(result):
            return await result
        return result


def tool(
    name: str,
    description: str,
    input_model: type[BaseModel],
    is_read_only: bool = False,
    is_concurrency_safe: bool = False,
) -> Callable:
    """Decorator to create a tool from an async function.

    Example:
        class ReadFileInput(BaseModel):
            path: str

        @tool("read_file", "Read a file from disk", ReadFileInput, is_read_only=True, is_concurrency_safe=True)
        async def read_file(input: ReadFileInput, context: AgentContext) -> ToolResult:
            content = open(input.path).read()
            return ToolResult(content=content)
    """

    def decorator(func: Callable[..., Awaitable[ToolResult]]) -> _FunctionTool:
        return _FunctionTool(
            func=func,
            name=name,
            description=description,
            input_model=input_model,
            is_read_only=is_read_only,
            is_concurrency_safe=is_concurrency_safe,
        )

    return decorator


class ToolRegistry:
    """Central tool registry. Mirrors Claude Code's Tools type + findToolByName().

    Supports registration, lookup, filtering (for sub-agent tool scoping),
    and bulk conversion to ToolDefinition for LLM API calls.
    """

    def __init__(self, tools: list[BaseTool] | None = None):
        self._tools: dict[str, BaseTool] = {}
        if tools:
            for t in tools:
                self.register(t)

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list(self) -> list[BaseTool]:
        return list(self._tools.values())

    def names(self) -> set[str]:
        return set(self._tools.keys())

    def definitions(self) -> list[ToolDefinition]:
        """All tools as ToolDefinition for LLM API calls."""
        return [t.to_definition() for t in self._tools.values()]

    def filter(
        self,
        names: set[str] | None = None,
        exclude: set[str] | None = None,
    ) -> ToolRegistry:
        """Create a filtered copy. Used for sub-agent tool scoping."""
        filtered = []
        for t in self._tools.values():
            if names is not None and t.name not in names:
                continue
            if exclude is not None and t.name in exclude:
                continue
            filtered.append(t)
        return ToolRegistry(filtered)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
