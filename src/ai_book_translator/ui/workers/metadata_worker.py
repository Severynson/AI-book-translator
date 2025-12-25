from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.infrastructure.llm.base import LLMProvider
from ai_book_translator.services.metadata_service import MetadataService
from ai_book_translator.infrastructure.persistence.metadata_cache import (
    save_metadata_cache,
)
from ai_book_translator.infrastructure.persistence.translation_state import (
    compute_document_hash,
)

try:
    from ai_book_translator.infrastructure.io.read_document.base import ReadDocument
except Exception:
    ReadDocument = None


class MetadataWorker(QThread):
    progressed = pyqtSignal(int, str)  # pct, stage
    succeeded = pyqtSignal(object)  # MetadataResult
    failed = pyqtSignal(str)

    def __init__(
        self,
        provider: LLMProvider,
        settings: Settings,
        document: DocumentInput,
        target_language: str,
        display_name: str = "",
    ):
        super().__init__()
        self.provider = provider
        self.settings = settings
        self.document = document
        self.target_language = target_language
        self.display_name = display_name or "document"

    def run(self) -> None:
        try:
            self.progressed.emit(5, "Preparing document…")

            doc = self.document
            if doc.raw_text is None and doc.file_path and ReadDocument is not None:
                try:
                    txt = ReadDocument.from_path(doc.file_path).read(doc.file_path)
                    doc = DocumentInput(file_path=doc.file_path, raw_text=txt)
                except Exception:
                    doc = self.document

            self.progressed.emit(
                15, f"Generating metadata JSON for {self.display_name}…"
            )

            svc = MetadataService(self.provider, self.settings)
            res: MetadataResult = svc.generate_metadata(
                doc, target_language=self.target_language
            )

            doc_hash = compute_document_hash(doc.raw_text or "")
            title_hint = ""
            try:
                t = (res.metadata or {}).get("title")
                if isinstance(t, str):
                    title_hint = t
            except Exception:
                pass

            p = save_metadata_cache(
                document_hash=doc_hash,
                metadata=dict(res.metadata or {}),
                target_language=self.target_language,
                title_hint=title_hint,
            )
            self.progressed.emit(95, f"Cached metadata: {p}")

            self.progressed.emit(100, "Done")
            self.succeeded.emit(res)

        except Exception as e:
            self.failed.emit(str(e))
