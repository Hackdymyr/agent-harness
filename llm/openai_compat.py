"""OpenAI-compatible adapter for Ollama, vLLM, LM Studio, DeepSeek, etc."""

from __future__ import annotations

from typing import Any

from agent_harness.llm.openai import OpenAILLM


class OpenAICompatLLM(OpenAILLM):
    """Any OpenAI-compatible API endpoint.

    Usage:
        llm = OpenAICompatLLM(
            base_url="http://localhost:11434/v1",  # Ollama
            model="llama3",
            api_key="not-needed",
        )
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        **kwargs: Any,
    ):
        super().__init__(model=model, api_key=api_key, base_url=base_url, **kwargs)
