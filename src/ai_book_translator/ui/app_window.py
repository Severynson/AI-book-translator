from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any, Dict

from PyQt5.QtWidgets import QMainWindow, QStackedWidget, QMessageBox

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.domain.llm_config import (
    LLMConfig,
    config_to_dict,
    config_from_dict,
)
from ai_book_translator.domain.translation_checkpoint import TranslationCheckpoint
from ai_book_translator.infrastructure.llm.client import LLMClient
from ai_book_translator.infrastructure.llm.provider_factory import create_client
from ai_book_translator.services.document_service import ensure_raw_text, document_hash

from .pages.book_input_page import BookInputPage
from .pages.model_setup_page import ModelSetupPage
from .pages.metadata_page import MetadataPage
from .pages.translate_page import TranslatePage

from ai_book_translator.infrastructure.persistence.metadata_cache import (
    find_metadata_cache_by_hash,
    load_metadata_cache,
)
from ai_book_translator.infrastructure.persistence.translation_state import (
    find_state_by_hash,
    load_state,
    delete_state,
)


@dataclass
class AppState:
    client: Optional[LLMClient] = None
    llm_config: Optional[LLMConfig] = None
    target_language: str = "Ukrainian"
    settings: Optional[Settings] = None
    document: Optional[DocumentInput] = None
    metadata_result: Optional[MetadataResult] = None
    resume_checkpoint: Optional[TranslationCheckpoint] = None
    resume_state_path: Optional[str] = None
    system_prompt_customization: str = ""
    translation_instruction: str = ""


class AppWindow(QMainWindow):
    """Main application window.

    Page order (changed from original):
      0 — Book Input   (was page 1)
      1 — Model Setup   (was page 0)
      2 — Metadata
      3 — Translation
    """

    def __init__(self, settings: Settings):
        super().__init__()
        self._default_settings = settings
        self.state = AppState(settings=settings)

        self.setWindowTitle("AI-book-translator")
        self.resize(980, 720)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Page 0 — Book Input (first screen now)
        self.page_input = BookInputPage(
            on_next=self._on_document_ready, on_back=lambda: None
        )
        # Page 1 — Model Setup
        self.page_model = ModelSetupPage(on_success=self._on_model_ready)
        self.page_model.set_on_back(self._go_book_input)
        # Page 2 — Metadata
        self.page_metadata = MetadataPage(
            on_done=self._on_metadata_ready, on_back=self._go_book_input
        )
        # Page 3 — Translation
        self.page_translate = TranslatePage(on_back=self._go_book_input)

        self._stack.addWidget(self.page_input)     # idx 0
        self._stack.addWidget(self.page_model)     # idx 1
        self._stack.addWidget(self.page_metadata)  # idx 2
        self._stack.addWidget(self.page_translate)  # idx 3

        self._stack.setCurrentIndex(0)

    # ---- navigation helpers ----

    def _go_book_input(self) -> None:
        self._stack.setCurrentIndex(0)

    def _go_model_setup(self) -> None:
        self._stack.setCurrentIndex(1)

    def _go_metadata(self) -> None:
        self._stack.setCurrentIndex(2)
        self.page_metadata.start(
            client=self.state.client,
            settings=self.state.settings or self._default_settings,
            document=self.state.document,
            target_language=self.state.target_language,
        )

    def _go_translate(self) -> None:
        self._stack.setCurrentIndex(3)
        llm_config_dict = None
        if self.state.llm_config:
            try:
                llm_config_dict = config_to_dict(self.state.llm_config)
            except Exception:
                pass
        self.page_translate.start(
            client=self.state.client,
            settings=self.state.settings or self._default_settings,
            document=self.state.document,
            metadata_result=self.state.metadata_result,
            target_language=self.state.target_language,
            resume_checkpoint=self.state.resume_checkpoint,
            resume_state_path=self.state.resume_state_path,
            llm_config_dict=llm_config_dict,
            system_prompt_customization=self.state.system_prompt_customization,
            translation_instruction=self.state.translation_instruction,
        )

    # ---- callbacks ----

    def _on_document_ready(self, doc: DocumentInput) -> None:
        """Called when user submits a document on page 0.

        Resume priority:
        1. Translation checkpoint exists → ask Continue / Start over
        2. Cached metadata exists → skip metadata, go to model setup
        3. Neither → fresh flow via model setup
        """
        # Ensure raw_text for hashing and resume detection.
        # If extraction fails here, it will be retried later by
        # the metadata worker and translate page.
        try:
            doc = ensure_raw_text(doc)
        except Exception:
            pass  # upload-first path doesn't need raw_text yet

        self.state.document = doc
        self.state.resume_checkpoint = None
        self.state.resume_state_path = None
        self.state.metadata_result = None

        doc_hash: Optional[str] = None
        if doc.raw_text:
            try:
                doc_hash = document_hash(doc)
            except Exception:
                pass

        # 1) Check for incomplete translation
        if doc_hash:
            found = self._find_translation_state(doc_hash)
            if found:
                state_path, checkpoint = found
                self._show_resume_dialog(doc, doc_hash, state_path, checkpoint)
                return

        # 2) Check for cached metadata
        if doc_hash:
            meta_path = find_metadata_cache_by_hash(doc_hash)
            if meta_path:
                try:
                    rec = load_metadata_cache(meta_path)
                    self.state.metadata_result = MetadataResult(
                        metadata=dict(rec.metadata or {}),
                        strategy_used="cached_metadata",
                    )
                except Exception:
                    pass

        # 3) Normal flow → model setup
        self._go_model_setup()

    def _on_model_ready(
        self, client: LLMClient, target_language: str, settings: Settings, config: LLMConfig,
        system_prompt_customization: str = "", translation_instruction: str = "",
    ) -> None:
        self.state.client = client
        self.state.llm_config = config
        self.state.target_language = target_language
        self.state.settings = settings
        self.state.system_prompt_customization = system_prompt_customization
        self.state.translation_instruction = translation_instruction

        # If we already have metadata (cached), skip to translation
        if self.state.metadata_result:
            self._go_translate()
        else:
            self._go_metadata()

    def _on_metadata_ready(self, metadata_result: MetadataResult, enriched_doc: DocumentInput = None) -> None:
        self.state.metadata_result = metadata_result
        # Update document with raw_text populated by metadata worker
        if enriched_doc is not None and enriched_doc.raw_text:
            self.state.document = enriched_doc
        self._go_translate()

    # ---- resume logic ----

    def _find_translation_state(self, doc_hash: str):
        try:
            found = find_state_by_hash(doc_hash)
            if not found:
                return None
            path, raw_state = found
            checkpoint = TranslationCheckpoint.from_dict(raw_state)
            return path, checkpoint
        except Exception:
            return None

    def _show_resume_dialog(
        self,
        doc: DocumentInput,
        doc_hash: str,
        state_path,
        checkpoint: TranslationCheckpoint,
    ) -> None:
        progress_pct = 0
        if checkpoint.chunks_total > 0:
            progress_pct = int(
                (checkpoint.next_chunk_index / checkpoint.chunks_total) * 100
            )

        msg = QMessageBox(self)
        msg.setWindowTitle("Resume translation?")
        msg.setText(
            f"An incomplete translation for this document was found.\n\n"
            f"Progress: {checkpoint.next_chunk_index}/{checkpoint.chunks_total} "
            f"chunks ({progress_pct}%)\n"
            f"Target language: {checkpoint.target_language}\n\n"
            f"Do you want to continue where you left off, or start over?"
        )
        btn_continue = msg.addButton("Continue", QMessageBox.AcceptRole)
        btn_start_over = msg.addButton("Start over", QMessageBox.RejectRole)
        msg.exec_()

        if msg.clickedButton() == btn_continue:
            self._resume_translation(doc, doc_hash, state_path, checkpoint)
        else:
            # Delete old state, proceed with fresh flow
            try:
                delete_state(state_path)
            except Exception:
                pass
            self._go_model_setup()

    def _resume_translation(
        self,
        doc: DocumentInput,
        doc_hash: str,
        state_path,
        checkpoint: TranslationCheckpoint,
    ) -> None:
        """Reconstruct provider from saved config and skip to translation."""
        self.state.resume_checkpoint = checkpoint
        self.state.resume_state_path = str(state_path)
        self.state.target_language = checkpoint.target_language or self.state.target_language
        self.state.system_prompt_customization = checkpoint.system_prompt_customization or ""
        self.state.translation_instruction = checkpoint.translation_instruction or ""

        # Reconstruct settings from checkpoint
        if checkpoint.translation_chunk_chars:
            base = self._default_settings
            self.state.settings = Settings(
                upload_retries=base.upload_retries,
                json_repair_retries=base.json_repair_retries,
                translation_chunk_chars=checkpoint.translation_chunk_chars,
                local_metadata_chunk_chars=base.local_metadata_chunk_chars,
                local_metadata_first_chunks_with_title_author_hint=base.local_metadata_first_chunks_with_title_author_hint,
                max_chunk_summaries_for_summary_of_summaries=base.max_chunk_summaries_for_summary_of_summaries,
            )

        # Reconstruct LLM client from saved config
        if checkpoint.llm_config:
            try:
                config = config_from_dict(checkpoint.llm_config)
                self.state.llm_config = config
                self.state.client = create_client(config)
            except Exception:
                # Config reconstruction failed, ask user for new config
                self._go_model_setup()
                return
        else:
            # No saved config, ask user
            self._go_model_setup()
            return

        # Load metadata from cache
        meta_path = checkpoint.metadata_path
        if meta_path:
            try:
                rec = load_metadata_cache(meta_path)
                self.state.metadata_result = MetadataResult(
                    metadata=dict(rec.metadata or {}),
                    strategy_used="resume",
                )
            except Exception:
                pass

        if not self.state.metadata_result:
            # Try finding by hash
            mp = find_metadata_cache_by_hash(doc_hash)
            if mp:
                try:
                    rec = load_metadata_cache(mp)
                    self.state.metadata_result = MetadataResult(
                        metadata=dict(rec.metadata or {}),
                        strategy_used="resume",
                    )
                except Exception:
                    pass

        if not self.state.metadata_result:
            # Can't resume without metadata — fall back to model setup
            self._go_model_setup()
            return

        self._go_translate()
