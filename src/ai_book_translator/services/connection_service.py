from __future__ import annotations

from ..infrastructure.llm.client import LLMClient


class ConnectionService:
    def __init__(self, client: LLMClient):
        self._client = client

    def test(self) -> None:
        self._client.test_connection()
