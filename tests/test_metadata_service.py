import pytest

from ai_book_translator.services.metadata_service import MetadataService
from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput
from ai_book_translator.infrastructure.llm.types import (
    LLMCapabilities,
    LLMRequest,
    LLMResponse,
)
from ai_book_translator.infrastructure.llm.exceptions import (
    UploadNotSupportedError,
    UploadFailedError,
    TransientLLMError,
    DocumentReadError,
    InvalidJSONError,
)

import json


class FakeClient:
    """LLMClient stub with scripted behavior."""

    def __init__(
        self,
        *,
        supports_upload: bool = True,
        supports_schema: bool = True,
    ):
        self._caps = LLMCapabilities(
            supports_file_upload=supports_upload,
            supports_json_schema=supports_schema,
        )
        self.calls: list = []
        self.responses: list = []  # list of str or Exception

    def capabilities(self) -> LLMCapabilities:
        return self._caps

    def test_connection(self) -> None:
        pass

    def generate_text(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if not self.responses:
            return LLMResponse(text="{}")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return LLMResponse(text=r)


@pytest.fixture
def settings():
    return Settings(
        upload_retries=2,
        json_repair_retries=1,
        translation_chunk_chars=30000,
        local_metadata_chunk_chars=20,
        local_metadata_first_chunks_with_title_author_hint=1,
        max_chunk_summaries_for_summary_of_summaries=3,
    )


VALID_META = {
    "author(s)": "A",
    "title": "T",
    "language": ["en"],
    "summary": "S",
    "chapters": {
        "ch1": {"general": "g1", "detailed": "d1"}
    },
}


def test_upload_success(settings):
    client = FakeClient()
    # Schema attempt returns valid JSON
    client.responses = [json.dumps(VALID_META)]
    svc = MetadataService(client, settings)

    doc = DocumentInput(file_path="book.pdf", raw_text=None)
    res = svc.generate_metadata(doc, target_language="uk")

    assert res.strategy_used == "upload"
    assert res.fallback_reason is None
    assert res.metadata["target_language"] == "uk"
    assert len(client.calls) >= 1
    # First call should have file_path set
    assert client.calls[0].file_path == "book.pdf"


def test_upload_not_supported_falls_back_to_chunked(settings):
    client = FakeClient(supports_upload=False)

    # Chunk summaries (plain text responses)
    chunk_responses = ["sum1", "sum2", "sum3"]
    # Summary-of-summaries returns valid JSON
    sos_meta = {**VALID_META, "chapters": {}}
    all_responses = chunk_responses + [json.dumps(sos_meta)]
    client.responses = all_responses

    doc = DocumentInput(
        file_path="book.pdf", raw_text="This is a book text that will be chunked."
    )
    res = svc = MetadataService(client, settings)
    res = svc.generate_metadata(doc, target_language="pl")

    assert res.strategy_used == "chunked"
    assert "does not support file upload" in (res.fallback_reason or "")
    assert res.metadata["target_language"] == "pl"


def test_no_file_path_uses_chunked(settings):
    client = FakeClient()

    chunk_responses = ["sum1", "sum2", "sum3"]
    sos_meta = {**VALID_META, "chapters": {}}
    client.responses = chunk_responses + [json.dumps(sos_meta)]

    svc = MetadataService(client, settings)
    doc = DocumentInput(file_path=None, raw_text="Some long book text here...")
    res = svc.generate_metadata(doc, target_language="de")

    assert res.strategy_used == "chunked"
    assert res.fallback_reason == "no file provided for upload"
    assert res.metadata["target_language"] == "de"


def test_chunked_requires_raw_text(settings):
    client = FakeClient()
    svc = MetadataService(client, settings)

    doc = DocumentInput(file_path=None, raw_text=None)

    with pytest.raises(DocumentReadError):
        svc.generate_metadata(doc, target_language="en")


def test_upload_transient_retry_then_success(settings):
    client = FakeClient()
    # First call fails with transient, second succeeds
    client.responses = [
        TransientLLMError("timeout"),
        json.dumps(VALID_META),
    ]

    svc = MetadataService(client, settings)
    doc = DocumentInput(file_path="book.pdf", raw_text="fallback text just in case")
    res = svc.generate_metadata(doc, target_language="uk")

    assert res.strategy_used == "upload"
    assert len(client.calls) == 2
    assert res.metadata["target_language"] == "uk"


def test_upload_invalid_json_triggers_repair(settings):
    client = FakeClient()
    # Schema attempt returns invalid JSON, prompt attempt also invalid,
    # repair loop should eventually produce valid JSON
    client.responses = [
        "NOT_JSON",     # schema attempt
        "NOT_JSON",     # prompt-only attempt
        json.dumps(VALID_META),  # repair attempt
    ]

    svc = MetadataService(client, settings)
    doc = DocumentInput(file_path="book.pdf", raw_text="fallback text")
    res = svc.generate_metadata(doc, target_language="es")

    assert res.strategy_used == "upload"
    assert res.metadata["target_language"] == "es"
