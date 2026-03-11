from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class LLMCapabilities:
    supports_file_upload: bool = False
    supports_json_schema: bool = False


@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    user_prompt: str
    file_path: Optional[str] = None
    json_schema: Optional[Dict[str, Any]] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


@dataclass(frozen=True)
class LLMResponse:
    text: str
    raw: Optional[Dict[str, Any]] = None
