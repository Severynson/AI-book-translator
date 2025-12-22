from __future__ import annotations
from ..infrastructure.llm.base import LLMProvider

class ConnectionService:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def test(self) -> None:
        self.provider.test_connection()
