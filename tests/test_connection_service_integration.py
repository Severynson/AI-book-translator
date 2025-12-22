# Test success varies a lot from run to run, since LLMs are unpredictable in their response,
# and max_tokens limit was set. Run multiple times or increase the limit if fails.

from dotenv import load_dotenv

load_dotenv()

import os
import socket
import pytest

from ai_book_translator.services.connection_service import ConnectionService

# Update these imports if your filenames differ:
from ai_book_translator.infrastructure.llm.openai_provider import (
    OpenAIResponsesProvider,
)
from ai_book_translator.infrastructure.llm.local_provider import LocalOllamaProvider


def _host_port_reachable(url: str, timeout: float = 0.5) -> bool:
    """
    Quick TCP reachability check for URLs like http://localhost:11434
    (avoid hanging tests if Ollama isn't running).
    """
    try:
        # naive parse: http(s)://host:port
        url = url.replace("https://", "").replace("http://", "")
        host_port = url.split("/")[0]
        host, port_str = host_port.split(":")
        port = int(port_str)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


@pytest.mark.integration
def test_connection_service_openai_from_env():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    provider = OpenAIResponsesProvider(api_key=api_key, model="gpt-5-nano")
    ConnectionService(provider).test()


@pytest.mark.integration
def test_connection_service_ollama_from_env():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL")

    if not _host_port_reachable(base_url):
        pytest.skip(
            f"Ollama not reachable at {base_url} (set OLLAMA_BASE_URL or start Ollama)"
        )

    provider = LocalOllamaProvider(base_url=base_url, model=model)
    ConnectionService(provider).test()
