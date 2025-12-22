import pytest

from ai_book_translator.services.metadata_service import MetadataService
from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput
from ai_book_translator.infrastructure.llm.exceptions import (
    UploadNotSupportedError,
    TransientLLMError,
    DocumentReadError,
    InvalidJSONError,
)


class FakeProvider:
    """
    Provider stub with scripted behavior.
    Set these attributes in tests to control responses.
    """

    def __init__(self):
        self.chat_text_calls = []
        self.chat_doc_calls = []

        self.doc_behaviors = []  # list of either dict result or exception
        self.text_behaviors = []  # list of str results (for chunk summaries)
        self.repair_behaviors = (
            []
        )  # list of dict results (for json repair / summary-of-summaries)

    def test_connection(self) -> None:
        return None

    def chat_text(self, system_prompt: str, user_prompt: str, **kwargs):
        self.chat_text_calls.append((system_prompt, user_prompt, kwargs))
        if not self.text_behaviors:
            return ""
        return self.text_behaviors.pop(0)

    def chat_text_with_document(
        self, system_prompt: str, user_prompt: str, file_path: str, **kwargs
    ):
        self.chat_doc_calls.append((system_prompt, user_prompt, file_path, kwargs))
        if not self.doc_behaviors:
            raise UploadNotSupportedError("no scripted upload result")
        b = self.doc_behaviors.pop(0)
        if isinstance(b, Exception):
            raise b
        # metadata_service expects raw string, then parse_json_strict will parse it;
        # in tests we monkeypatch parse_json_strict so we can return dict directly or use str.
        return b


@pytest.fixture
def settings():
    # Build with overrides (works for frozen dataclasses)
    return Settings(
        upload_retries=2,
        json_repair_retries=1,
        translation_chunk_chars=1800,
        local_metadata_chunk_chars=20,
        local_metadata_first_chunks_with_title_author_hint=1,
        max_chunk_summaries_for_summary_of_summaries=3,
    )


def _stub_schema_helpers(monkeypatch):
    # Make schema helpers no-ops for unit testing.
    monkeypatch.setattr(
        "ai_book_translator.services.metadata_service.validate_metadata_json",
        lambda meta: None,
    )
    monkeypatch.setattr(
        "ai_book_translator.services.metadata_service.normalize_not_provided",
        lambda meta: meta,
    )


def test_upload_success(monkeypatch, settings):
    _stub_schema_helpers(monkeypatch)

    provider = FakeProvider()
    provider.doc_behaviors = ["RAW_JSON"] 
    svc = MetadataService(provider, settings)

    # provider returns "raw json string"; parse_json_strict -> dict
    monkeypatch.setattr(
        "ai_book_translator.services.metadata_service.parse_json_strict",
        lambda raw: {
            "author(s)": "A",
            "title": "T",
            "language": "en",
            "summary": "S",
            "chapters": {},
        },
    )

    doc = DocumentInput(file_path="book.pdf", raw_text=None)
    res = svc.generate_metadata(doc, target_language="uk")

    assert res.strategy_used == "upload"
    assert res.fallback_reason is None
    assert res.metadata["target_language"] == "uk"
    assert provider.chat_doc_calls, "expected upload call"


def test_upload_not_supported_falls_back_to_chunked(monkeypatch, settings):
    _stub_schema_helpers(monkeypatch)

    provider = FakeProvider()
    svc = MetadataService(provider, settings)

    # Upload fails
    provider.doc_behaviors = [UploadNotSupportedError("no upload")]

    # Chunk summaries (3 max)
    provider.text_behaviors = ["sum1", "sum2", "sum3"]

    # summary-of-summaries JSON result
    monkeypatch.setattr(
        "ai_book_translator.services.metadata_service.chat_json_strict_with_repair",
        lambda **kwargs: {
            "author(s)": "A",
            "title": "T",
            "language": "en",
            "summary": "S",
            "chapters": {},
        },
    )

    doc = DocumentInput(
        file_path="book.pdf", raw_text="This is a book text that will be chunked."
    )
    res = svc.generate_metadata(doc, target_language="pl")

    assert res.strategy_used == "chunked"
    assert "no upload" in (res.fallback_reason or "")
    assert res.metadata["target_language"] == "pl"
    assert provider.chat_text_calls, "expected chunk summarization calls"


def test_no_file_path_uses_chunked(monkeypatch, settings):
    _stub_schema_helpers(monkeypatch)

    provider = FakeProvider()
    svc = MetadataService(provider, settings)

    provider.text_behaviors = ["sum1", "sum2", "sum3"]
    monkeypatch.setattr(
        "ai_book_translator.services.metadata_service.chat_json_strict_with_repair",
        lambda **kwargs: {
            "author(s)": "A",
            "title": "T",
            "language": "en",
            "summary": "S",
            "chapters": {},
        },
    )

    doc = DocumentInput(file_path=None, raw_text="Some long book text here...")
    res = svc.generate_metadata(doc, target_language="de")

    assert res.strategy_used == "chunked"
    assert res.fallback_reason == "no file provided for upload"
    assert res.metadata["target_language"] == "de"


def test_chunked_requires_raw_text(monkeypatch, settings):
    _stub_schema_helpers(monkeypatch)

    provider = FakeProvider()
    svc = MetadataService(provider, settings)

    doc = DocumentInput(file_path=None, raw_text=None)

    with pytest.raises(DocumentReadError):
        svc.generate_metadata(doc, target_language="en")


def test_upload_transient_retry_then_success(monkeypatch, settings):
    _stub_schema_helpers(monkeypatch)

    provider = FakeProvider()
    svc = MetadataService(provider, settings)

    # First call transient, second call succeeds
    provider.doc_behaviors = [
        TransientLLMError("timeout"),
        "RAW_JSON",
    ]

    monkeypatch.setattr(
        "ai_book_translator.services.metadata_service.parse_json_strict",
        lambda raw: {
            "author(s)": "A",
            "title": "T",
            "language": "en",
            "summary": "S",
            "chapters": {},
        },
    )

    doc = DocumentInput(file_path="book.pdf", raw_text="fallback text just in case")
    res = svc.generate_metadata(doc, target_language="uk")

    assert res.strategy_used == "upload"
    assert len(provider.chat_doc_calls) == 2, "should retry once then succeed"
    assert res.metadata["target_language"] == "uk"


def test_upload_invalid_json_triggers_repair(monkeypatch, settings):
    _stub_schema_helpers(monkeypatch)

    provider = FakeProvider()
    svc = MetadataService(provider, settings)

    provider.doc_behaviors = ["NOT_JSON"]

    def parse_fail(_raw):
        raise InvalidJSONError("bad json")

    monkeypatch.setattr(
        "ai_book_translator.services.metadata_service.parse_json_strict", parse_fail
    )

    # Repair returns valid dict
    monkeypatch.setattr(
        "ai_book_translator.services.metadata_service.chat_json_strict_with_repair",
        lambda **kwargs: {
            "author(s)": "A",
            "title": "T",
            "language": "en",
            "summary": "S",
            "chapters": {},
        },
    )

    doc = DocumentInput(file_path="book.pdf", raw_text="fallback text")
    res = svc.generate_metadata(doc, target_language="es")

    assert res.strategy_used == "upload"
    assert res.metadata["target_language"] == "es"
