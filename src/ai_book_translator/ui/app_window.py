from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any, Dict

from PyQt5.QtWidgets import QMainWindow, QStackedWidget

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.infrastructure.llm.base import LLMProvider

from .pages.model_setup_page import ModelSetupPage
from .pages.book_input_page import BookInputPage
from .pages.metadata_page import MetadataPage
from .pages.translate_page import TranslatePage


@dataclass
class AppState:
    provider: Optional[LLMProvider] = None
    target_language: str = "Ukrainian"
    document: Optional[DocumentInput] = None
    metadata_result: Optional[MetadataResult] = None
    translation_state: Optional[Dict[str, Any]] = None


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
        )

    def _on_model_ready(
        self, provider: LLMProvider, target_language: str, settings: Settings
    ) -> None:
        self.state.provider = provider
        self.state.target_language = target_language
        self.settings = settings
        self._go_book_input()

    def _on_document_ready(self, doc: DocumentInput) -> None:
        self.state.document = doc
        self._go_metadata()

    def _on_metadata_ready(self, metadata_result: MetadataResult) -> None:
        self.state.metadata_result = metadata_result
        self._go_translate()
