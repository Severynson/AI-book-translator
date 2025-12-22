from __future__ import annotations

import os
from typing import Callable, Optional

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QComboBox,
)

from ai_book_translator.config.settings import Settings
from ai_book_translator.infrastructure.llm.openai_provider import (
    OpenAIResponsesProvider,
)
from ai_book_translator.infrastructure.llm.local_provider import LocalOllamaProvider
from ai_book_translator.services.connection_service import ConnectionService

from ..widgets.error_banner import ErrorBanner


class ModelSetupPage(QWidget):
    """
    Step 0 — Model setup
    """

    def __init__(self, on_success: Callable[..., None]):
        super().__init__()
        self._on_success = on_success

        root = QVBoxLayout()
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel("Step 0 — Model setup")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        self.banner = ErrorBanner()

        # Provider selector
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Provider:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["openai", "ollama"])
        self.provider_combo.currentTextChanged.connect(self._sync_visibility)
        provider_row.addWidget(self.provider_combo)
        provider_row.addStretch(1)

        # OpenAI
        self.openai_key = QLineEdit()
        self.openai_key.setPlaceholderText("sk-proj-kn... (OPENAI_API_KEY)")
        self.openai_model = QLineEdit()
        self.openai_model.setPlaceholderText("gpt-5-nano")

        # Ollama
        self.ollama_base_url = QLineEdit()
        self.ollama_base_url.setPlaceholderText("http://localhost:11434")
        self.ollama_model = QLineEdit()
        self.ollama_model.setPlaceholderText("llama3.1")

        # Target language
        self.target_language = QLineEdit()
        self.target_language.setPlaceholderText("e.g., Ukrainian")

        # translation chunk size
        chunk_row = QHBoxLayout()
        chunk_row.addWidget(QLabel("Chunk size (chars):"))
        self.chunk_chars = QLineEdit()
        self.chunk_chars.setPlaceholderText("30 000")
        self.chunk_chars.setFixedWidth(120)
        chunk_row.addWidget(self.chunk_chars)
        chunk_row.addStretch(1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_continue = QPushButton("Continue")
        self.btn_continue.clicked.connect(self._handle_continue)
        btn_row.addWidget(self.btn_continue)

        # Layout
        root.addWidget(title)
        root.addWidget(self.banner)
        root.addLayout(provider_row)

        root.addWidget(QLabel("OpenAI API key:"))
        root.addWidget(self.openai_key)
        root.addWidget(QLabel("OpenAI model:"))
        root.addWidget(self.openai_model)

        root.addWidget(QLabel("Ollama base URL:"))
        root.addWidget(self.ollama_base_url)
        root.addWidget(QLabel("Ollama model:"))
        root.addWidget(self.ollama_model)

        root.addWidget(QLabel("Target language:"))
        root.addWidget(self.target_language)

        root.addLayout(chunk_row)
        root.addLayout(btn_row)

        self.setLayout(root)
        self._sync_visibility(self.provider_combo.currentText())

    def _sync_visibility(self, provider_name: str) -> None:
        is_openai = provider_name == "openai"

        self.openai_key.setEnabled(is_openai)
        self.openai_model.setEnabled(is_openai)

        self.ollama_base_url.setEnabled(not is_openai)
        self.ollama_model.setEnabled(not is_openai)

    def _parse_chunk_chars(self, s: str) -> Optional[int]:
        raw = (s or "").strip()
        if not raw:
            return None
        n = int(raw)
        if n < 200 or n > 200_000:
            raise ValueError("chunk size out of range")
        return n

    def _settings_with_optional_override(self) -> Settings:
        base = Settings()
        override = self._parse_chunk_chars(self.chunk_chars.text())
        if override is None:
            return base

        # Settings is frozen=True => construct a new instance with the override
        return Settings(
            upload_retries=base.upload_retries,
            json_repair_retries=base.json_repair_retries,
            translation_chunk_chars=override,
            local_metadata_chunk_chars=base.local_metadata_chunk_chars,
            local_metadata_first_chunks_with_title_author_hint=base.local_metadata_first_chunks_with_title_author_hint,
            max_chunk_summaries_for_summary_of_summaries=base.max_chunk_summaries_for_summary_of_summaries,
        )

    def _handle_continue(self) -> None:
        self.banner.hide()

        provider_name = self.provider_combo.currentText().strip()
        target_lang = (self.target_language.text() or "").strip()
        if not target_lang:
            self.banner.show_error("Please enter target language.")
            return

        # Build settings (with optional override)
        try:
            settings = self._settings_with_optional_override()
        except Exception:
            self.banner.show_error(
                "Chunk size must be an integer between 200 and 200000."
            )
            return

        # Create provider
        try:
            if provider_name == "openai":
                api_key = (self.openai_key.text() or "").strip() or os.getenv(
                    "OPENAI_API_KEY", ""
                )
                model = (self.openai_model.text() or "").strip() or "gpt-5-nano"
                if not api_key:
                    self.banner.show_error(
                        "OpenAI API key is missing. Enter it or set OPENAI_API_KEY."
                    )
                    return
                provider = OpenAIResponsesProvider(api_key=api_key, model=model)
            else:
                base_url = (
                    self.ollama_base_url.text() or ""
                ).strip() or "http://localhost:11434"
                model = (self.ollama_model.text() or "").strip() or "llama3.1"
                provider = LocalOllamaProvider(base_url=base_url, model=model)

            # Test connection before continuing
            ConnectionService(provider).test()

        except Exception as e:
            self.banner.show_error(str(e))
            return

        # pass settings forward
        self._on_success(provider, target_lang, settings)
