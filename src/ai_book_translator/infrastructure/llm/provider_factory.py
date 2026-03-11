from __future__ import annotations

from ...domain.llm_config import LLMConfig, OpenAIConfig, OllamaConfig
from .client import LLMClient
from .providers.openai_responses_adapter import OpenAIResponsesAdapter
from .providers.ollama_chat_adapter import OllamaChatAdapter


def create_client(config: LLMConfig) -> LLMClient:
    """Build an LLMClient from a typed config object."""
    if isinstance(config, OpenAIConfig):
        return OpenAIResponsesAdapter(config)
    if isinstance(config, OllamaConfig):
        return OllamaChatAdapter(config)
    raise ValueError(f"Unknown config type: {type(config)}")
