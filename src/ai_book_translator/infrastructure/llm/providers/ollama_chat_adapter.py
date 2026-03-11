from __future__ import annotations

from typing import Any, Dict

import requests

from ..types import LLMCapabilities, LLMRequest, LLMResponse
from ..exceptions import LLMError, TransientLLMError
from ....domain.llm_config import OllamaConfig


class OllamaChatAdapter:
    """OpenAI-compatible Ollama adapter implementing the LLMClient protocol."""

    def __init__(self, config: OllamaConfig):
        self._config = config
        self.base_url = config.base_url.rstrip("/")
        self.model = config.model
        self.timeout_sec = config.timeout_sec

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_file_upload=False,
            supports_json_schema=False,
        )

    def test_connection(self) -> None:
        self.generate_text(
            LLMRequest(
                system_prompt="You are a helpful assistant.",
                user_prompt="Reply with exactly: OK",
                max_tokens=64,
            )
        )

    def generate_text(self, request: LLMRequest) -> LLMResponse:
        url = f"{self.base_url}/v1/chat/completions"

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }

        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        try:
            r = requests.post(url, json=payload, timeout=self.timeout_sec)
        except requests.Timeout as e:
            raise TransientLLMError(f"Timeout calling {url}") from e
        except requests.RequestException as e:
            raise TransientLLMError(f"Network error calling {url}: {e}") from e

        if r.status_code in (429, 500, 502, 503, 504):
            raise TransientLLMError(f"Transient error {r.status_code}: {r.text[:500]}")
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:1200]}")

        data = r.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except Exception as e:
            raise LLMError(f"Unexpected response shape: {data}") from e

        return LLMResponse(text=text, raw=data)
