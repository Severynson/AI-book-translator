from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any, Dict
import hashlib

from PyQt5.QtWidgets import QMainWindow, QStackedWidget

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.infrastructure.llm.base import LLMProvider

from .pages.model_setup_page import ModelSetupPage
from .pages.book_input_page import BookInputPage
from .pages.metadata_page import MetadataPage
from .pages.translate_page import TranslatePage

from ai_book_translator.infrastructure.persistence.metadata_cache import (
    find_metadata_cache_by_hash,
    load_metadata_cache,
)

try:
    from ai_book_translator.infrastructure.io.read_document.base import ReadDocument
except Exception:
    ReadDocument = None


def _doc_hash_from_text(text: str) -> str:
    b = (text or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(b).hexdigest()


# ---- Translation resume (adapt imports to your actual module) ----
try:
    from ai_book_translator.infrastructure.persistence.translation_state import (
        find_state_by_hash,
        load_state,
    )
except Exception:
    find_state_by_hash = None
    load_state = None


@dataclass
class AppState:
    provider: Optional[LLMProvider] = None
    target_language: str = "Ukrainian"
    document: Optional[DocumentInput] = None
    metadata_result: Optional[MetadataResult] = None
    translation_state: Optional[Dict[str, Any]] = None
    translation_state_path: Optional[str] = None


class AppWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.state = AppState()

        self.setWindowTitle("AI-book-translator")
        self.resize(980, 720)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self.page_model = ModelSetupPage(on_success=self._on_model_ready)
        self.page_input = BookInputPage(
            on_next=self._on_document_ready, on_back=self._go_model_setup
        )
        self.page_metadata = MetadataPage(
            on_done=self._on_metadata_ready, on_back=self._go_book_input
        )
        self.page_translate = TranslatePage(on_back=self._go_book_input)

        self._stack.addWidget(self.page_model)  # idx 0
        self._stack.addWidget(self.page_input)  # idx 1
        self._stack.addWidget(self.page_metadata)  # idx 2
        self._stack.addWidget(self.page_translate)  # idx 3

        self._stack.setCurrentIndex(0)

    def _go_model_setup(self) -> None:
        self._stack.setCurrentIndex(0)

    def _go_book_input(self) -> None:
        self._stack.setCurrentIndex(1)

    def _go_metadata(self) -> None:
        self._stack.setCurrentIndex(2)
        self.page_metadata.start(
            provider=self.state.provider,
            settings=self.settings,
            document=self.state.document,
            target_language=self.state.target_language,
        )

    def _go_translate(self) -> None:
        self._stack.setCurrentIndex(3)
        self.page_translate.start(
            provider=self.state.provider,
            settings=self.settings,
            document=self.state.document,
            metadata_result=self.state.metadata_result,
            target_language=self.state.target_language,
            resume_state=self.state.translation_state,
            resume_state_path=self.state.translation_state_path,
        )

    def _on_model_ready(
        self, provider: LLMProvider, target_language: str, settings: Settings
    ) -> None:
        self.state.provider = provider
        self.state.target_language = target_language
        self.settings = settings
        self._go_book_input()

    def _on_document_ready(self, doc: DocumentInput) -> None:
        """
        New behavior:
        - Ensure raw_text exists if possible (needed for hashing + local fallbacks)
        - Compute document_hash from FULL TEXT
        - Resume priority:
            1) translation state
            2) metadata cache
            3) fresh metadata generation
        """
        # Ensure raw_text (for hashing)
        if doc.raw_text is None and doc.file_path and ReadDocument is not None:
            try:
                raw = ReadDocument.from_path(doc.file_path).read(doc.file_path)
                doc = DocumentInput(file_path=doc.file_path, raw_text=raw)
            except Exception:
                # keep as-is; may still work via upload-first metadata
                pass

        self.state.document = doc

        # Reset state related to previous document
        self.state.translation_state = None
        self.state.translation_state_path = None
        self.state.metadata_result = None

        doc_hash: Optional[str] = None
        if doc.raw_text:
            doc_hash = _doc_hash_from_text(doc.raw_text)

        # 1) Try resume translation first (if your state_store supports it)
        if doc_hash and find_state_by_hash:
            try:
                found = find_state_by_hash(doc_hash)
                if found:
                    p, st = found
                    self.state.translation_state = st
                    self.state.translation_state_path = str(p)

                    # If your TranslationWorker reads state directly, you may not need metadata_result here.
                    # But we try to populate metadata_result if available in state.
                    meta = st.get("metadata")
                    
                    # Handle metadata_path if full metadata object is missing (new schema) ---
                    if not meta and "metadata_path" in st:
                        try:
                            mpath = st["metadata_path"]
                            if mpath:
                                rec = load_metadata_cache(mpath)
                                if rec and rec.metadata:
                                    meta = rec.metadata
                        except Exception:
                            pass
                    # -------------------------------------------------------------------------------

                    if isinstance(meta, dict) and meta:
                        self.state.metadata_result = MetadataResult(
                            metadata=meta,
                            strategy_used="resume",
                            fallback_reason=None,
                        )
                    self._go_translate()
                    return
            except Exception:
                # If resume load fails, continue to metadata cache/fresh metadata
                pass

        # 2) Try reuse cached metadata (metadata-only resume)
        if doc_hash:
            p2 = find_metadata_cache_by_hash(doc_hash)
            if p2:
                try:
                    rec = load_metadata_cache(p2)
                    self.state.metadata_result = MetadataResult(
                        metadata=dict(rec.metadata or {}),
                        strategy_used="cached_metadata",
                        fallback_reason=None,
                    )
                    self._go_translate()
                    return
                except Exception:
                    pass

        # 3) No resume possible -> run metadata extraction
        self._go_metadata()

    def _on_metadata_ready(self, metadata_result: MetadataResult) -> None:
        self.state.metadata_result = metadata_result
        self._go_translate()
