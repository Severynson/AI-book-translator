from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import LLMCapabilities, LLMRequest, LLMResponse


@runtime_checkable
class LLMClient(Protocol):
    """Provider-agnostic LLM interface.

    All provider-specific details (endpoint URLs, auth, response formats)
    are hidden behind this protocol.  Services depend only on this interface.
    """

    def capabilities(self) -> LLMCapabilities: ...

    def test_connection(self) -> None: ...

    def generate_text(self, request: LLMRequest) -> LLMResponse: ...
