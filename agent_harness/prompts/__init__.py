"""agent_harness.prompts — Rich prompt engineering module.

Provides section-based system prompt composition, pre-defined agent type
profiles, environment detection, session guidance, and enriched tool
descriptions. Ported from Claude Code's prompt architecture.

Quick start:
    from agent_harness.prompts import SystemPromptBuilder, AgentType, enrich_tools

    # Option 1: Use a pre-defined agent profile
    builder = SystemPromptBuilder.for_agent_type(AgentType.GENERAL)
    prompt = builder.build()

    # Option 2: Build custom prompts from sections
    builder = SystemPromptBuilder()
    builder.add_section(PromptSection(name="role", content="You are...", priority=SectionPriority.AGENT))
    prompt = builder.build()

    # Enrich built-in tool descriptions
    enriched_registry = enrich_tools(original_registry)
"""

from agent_harness.prompts.sections import PromptSection, SectionPriority
from agent_harness.prompts.builder import SystemPromptBuilder
from agent_harness.prompts.agent_types import AgentType
from agent_harness.prompts.environment import compute_environment_info
from agent_harness.prompts.session import generate_session_guidance
from agent_harness.prompts.tool_descriptions import enrich_tools, get_rich_description

__all__ = [
    "PromptSection",
    "SectionPriority",
    "SystemPromptBuilder",
    "AgentType",
    "compute_environment_info",
    "generate_session_guidance",
    "enrich_tools",
    "get_rich_description",
]
