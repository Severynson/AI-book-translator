from __future__ import annotations

from ai_book_translator.domain.models import DocumentInput
from ai_book_translator.infrastructure.io.read_document.base import ReadDocument
from ai_book_translator.infrastructure.persistence.translation_state import (
    compute_document_hash,
)


def ensure_raw_text(doc: DocumentInput) -> DocumentInput:
    """Extract raw_text from file if not already present.

    Returns a new DocumentInput with raw_text populated (or the original
    if extraction is not possible).
    """
    if doc.raw_text is not None:
        return doc

    if not doc.file_path:
        return doc

    reader = ReadDocument.from_path(
        doc.file_path,
        use_ocr=doc.use_ocr,
        ocr_languages=doc.ocr_languages,
    )
    raw = reader.read(doc.file_path)
    return DocumentInput(
        file_path=doc.file_path,
        raw_text=raw,
        filename_hint=doc.filename_hint,
        use_ocr=doc.use_ocr,
        ocr_languages=doc.ocr_languages,
    )


def document_hash(doc: DocumentInput) -> str:
    """Compute deterministic hash from document text."""
    return compute_document_hash(doc.raw_text or "")
