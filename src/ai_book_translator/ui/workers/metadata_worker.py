from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.infrastructure.llm.client import LLMClient
from ai_book_translator.services.metadata_service import MetadataService
from ai_book_translator.services.document_service import ensure_raw_text, document_hash
from ai_book_translator.infrastructure.persistence.metadata_cache import (
    save_metadata_cache,
)


class MetadataWorker(QThread):
    progressed = pyqtSignal(int, str)  # pct, stage
    succeeded = pyqtSignal(object)  # MetadataResult
    failed = pyqtSignal(str)

    def __init__(
        self,
        client: LLMClient,
        settings: Settings,
        document: DocumentInput,
        target_language: str,
        display_name: str = "",
    ):
        super().__init__()
        self._client = client
        self._settings = settings
        self._document = document
        self._target_language = target_language
        self._display_name = display_name or "document"

    def run(self) -> None:
        try:
            self.progressed.emit(5, "Preparing document…")

            doc = self._document
            try:
                doc = ensure_raw_text(doc)
            except Exception:
                doc = self._document

            self.progressed.emit(
                15, f"Generating metadata JSON for {self._display_name}…"
            )

            svc = MetadataService(self._client, self._settings)
            res: MetadataResult = svc.generate_metadata(
                doc, target_language=self._target_language
            )

            doc_hash_val = document_hash(doc)
            title_hint = ""
            try:
                t = (res.metadata or {}).get("title")
                if isinstance(t, str):
                    title_hint = t
            except Exception:
                pass

            p = save_metadata_cache(
                document_hash=doc_hash_val,
                metadata=dict(res.metadata or {}),
                target_language=self._target_language,
                title_hint=title_hint,
            )
            self.progressed.emit(95, f"Cached metadata: {p}")

            self.progressed.emit(100, "Done")
            self.succeeded.emit(res)

        except Exception as e:
            self.failed.emit(str(e))
