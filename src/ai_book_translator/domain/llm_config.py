from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Union


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str = "gpt-5-nano"
    base_url: str = "https://api.openai.com"
    timeout_sec: int = 1000


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1"
    timeout_sec: int = 240


LLMConfig = Union[OpenAIConfig, OllamaConfig]


def config_to_dict(config: LLMConfig) -> Dict[str, Any]:
    if isinstance(config, OpenAIConfig):
        return {"provider_type": "openai", **asdict(config)}
    if isinstance(config, OllamaConfig):
        return {"provider_type": "ollama", **asdict(config)}
    raise ValueError(f"Unknown config type: {type(config)}")


def config_from_dict(d: Dict[str, Any]) -> LLMConfig:
    pt = d.get("provider_type", "")
    if pt == "openai":
        return OpenAIConfig(
            api_key=d.get("api_key") or os.getenv("OPENAI_API_KEY", ""),
            model=d.get("model", "gpt-5-nano"),
            base_url=d.get("base_url", "https://api.openai.com"),
            timeout_sec=int(d.get("timeout_sec", 1000)),
        )
    if pt == "ollama":
        return OllamaConfig(
            base_url=d.get("base_url", "http://localhost:11434"),
            model=d.get("model", "llama3.1"),
            timeout_sec=int(d.get("timeout_sec", 240)),
        )
    raise ValueError(f"Unknown provider_type: {pt!r}")
