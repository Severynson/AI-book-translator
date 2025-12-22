from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict
from .exceptions import UploadNotSupportedError

class LLMProvider(ABC):
    @abstractmethod
    def test_connection(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def chat_text(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    def chat_text_with_document(self, system_prompt: str, user_prompt: str, file_path: str, **kwargs: Any) -> str:
        raise UploadNotSupportedError("This provider does not support document upload.")
