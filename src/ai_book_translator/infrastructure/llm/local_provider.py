# src/ai_book_translator/infrastructure/llm/local_ollama_provider.py

from __future__ import annotations

from typing import Any, Dict, Optional
import requests

from .base import LLMProvider
from .exceptions import (
    LLMError,
    UploadNotSupportedError,
    TransientLLMError,
)

class LocalOllamaProvider(LLMProvider):
    """
    Local provider for an OpenAI-compatible Ollama server.
    Expected endpoints:
      - POST {base_url}/v1/chat/completions
    """

    def __init__(self, base_url: str, model: str, timeout_sec: int = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec

    def test_connection(self) -> None:
        _ = self.chat_text(
            system_prompt="You are a helpful assistant.",
            user_prompt="Reply with exactly: OK",
            temperature=0,
            max_tokens=8,
        )

    def chat_text(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        payload.update(kwargs)

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
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise LLMError(f"Unexpected response shape: {data}") from e

    def chat_text_with_document(
        self,
        system_prompt: str,
        user_prompt: str,
        file_path: str,
        **kwargs: Any,
    ) -> str:
        # Local LLM path: no doc upload; your MetadataService will catch this and fall back to chunking.
        raise UploadNotSupportedError("Local provider does not support document upload.")