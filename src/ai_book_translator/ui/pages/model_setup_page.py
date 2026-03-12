from __future__ import annotations

import os
from typing import Callable, Optional

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QComboBox,
    QTextEdit,
    QScrollArea,
    QSizePolicy,
    QFrame,
)
from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.llm_config import (
    LLMConfig,
    OpenAIConfig,
    OllamaConfig,
)
from ai_book_translator.infrastructure.llm.provider_factory import create_client
from ai_book_translator.services.connection_service import ConnectionService
from ai_book_translator.infrastructure.persistence.field_history import (
    get_field_values,
    push_many,
)

from ..widgets.error_banner import ErrorBanner


# Field keys for history persistence
_FK_OPENAI_KEY = "openai_api_key"
_FK_OPENAI_MODEL = "openai_model"
_FK_OLLAMA_URL = "ollama_base_url"
_FK_OLLAMA_MODEL = "ollama_model"
_FK_TARGET_LANG = "target_language"
_FK_CHUNK_CHARS = "chunk_chars"
_FK_SYS_CUSTOM = "system_prompt_customization"
_FK_TRANS_INSTR = "translation_instruction"


def _make_short_combo(placeholder: str, field_key: str) -> QComboBox:
    """Editable QComboBox for short single-line fields (model name, language, etc.)."""
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.lineEdit().setPlaceholderText(placeholder)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    combo.setMaximumWidth(600)

    history = get_field_values(field_key)
    if history:
        combo.addItems(history)
        combo.setCurrentIndex(0)
    else:
        combo.setCurrentIndex(-1)

    return combo


class _LongTextWithHistory(QWidget):
    """A text editor with a history dropdown for long-form fields.

    Combines a QComboBox (for picking from history) with a QTextEdit
    (for editing, with word-wrap and vertical growth).
    """

    def __init__(self, placeholder: str, field_key: str, min_height: int = 50):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # History dropdown
        self._history_combo = QComboBox()
        self._history_combo.setEditable(False)
        self._history_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        history = get_field_values(field_key)
        self._history_combo.addItem("-- select from history --")
        for val in history:
            # Show truncated preview in dropdown
            preview = val[:80] + "..." if len(val) > 80 else val
            self._history_combo.addItem(preview, val)

        if not history:
            self._history_combo.setVisible(False)

        self._history_combo.currentIndexChanged.connect(self._on_history_selected)

        # Text editor (wraps text, grows vertically)
        self._editor = QTextEdit()
        self._editor.setPlaceholderText(placeholder)
        self._editor.setAcceptRichText(False)
        self._editor.setLineWrapMode(QTextEdit.WidgetWidth)
        self._editor.setMinimumHeight(min_height)
        self._editor.setMaximumHeight(120)
        self._editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Pre-fill with most recent history value
        if history:
            self._editor.setPlainText(history[0])

        layout.addWidget(self._history_combo)
        layout.addWidget(self._editor)
        self.setLayout(layout)

    def _on_history_selected(self, index: int) -> None:
        if index <= 0:
            return
        full_value = self._history_combo.itemData(index)
        if full_value:
            self._editor.setPlainText(full_value)
        # Reset dropdown to placeholder
        self._history_combo.setCurrentIndex(0)

    def text(self) -> str:
        return self._editor.toPlainText().strip()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._history_combo.setEnabled(enabled)
        self._editor.setEnabled(enabled)


class ModelSetupPage(QWidget):
    """Model setup page. Builds an LLMConfig, creates a client via factory,
    tests connection, and passes config + client forward."""

    def __init__(self, on_success: Callable[..., None]):
        super().__init__()
        self._on_success = on_success

        # Outer layout with scroll area
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        root = QVBoxLayout()
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel("Step 2 — Model setup")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        self.banner = ErrorBanner()

        # Provider selector
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Provider:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["openai", "ollama"])
        self.provider_combo.currentTextChanged.connect(self._sync_visibility)
        self.provider_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        provider_row.addWidget(self.provider_combo)
        provider_row.addStretch(1)

        # OpenAI fields
        self.openai_key = _LongTextWithHistory(
            "sk-proj-kn... (OPENAI_API_KEY)", _FK_OPENAI_KEY, min_height=36
        )
        self.openai_model = _make_short_combo("gpt-5-nano", _FK_OPENAI_MODEL)

        # Ollama fields
        self.ollama_base_url = _make_short_combo(
            "http://localhost:11434", _FK_OLLAMA_URL
        )
        self.ollama_model = _make_short_combo("llama3.1", _FK_OLLAMA_MODEL)

        # Target language
        self.target_language = _make_short_combo("e.g., Ukrainian", _FK_TARGET_LANG)

        # Chunk size
        chunk_row = QHBoxLayout()
        chunk_row.addWidget(QLabel("Chunk size (chars):"))
        self.chunk_chars = _make_short_combo("30 000", _FK_CHUNK_CHARS)
        self.chunk_chars.setMaximumWidth(150)
        chunk_row.addWidget(self.chunk_chars)
        chunk_row.addStretch(1)

        # Custom translation instructions (long text with history)
        self.system_prompt_customization = _LongTextWithHistory(
            "Optional: additional system prompt instructions (e.g., 'modernize archaic language')",
            _FK_SYS_CUSTOM,
        )
        self.translation_instruction = _LongTextWithHistory(
            "Optional: per-run translation instruction (e.g., 'preserve original formatting strictly')",
            _FK_TRANS_INSTR,
        )

        # Buttons
        btn_row = QHBoxLayout()
        btn_back = QPushButton("Back")
        btn_back.clicked.connect(self._handle_back)
        btn_row.addWidget(btn_back)
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

        root.addWidget(QLabel("System prompt customization:"))
        root.addWidget(self.system_prompt_customization)
        root.addWidget(QLabel("Translation instruction:"))
        root.addWidget(self.translation_instruction)

        root.addLayout(btn_row)
        root.addStretch(1)

        content.setLayout(root)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.setLayout(outer)

        self._on_back: Optional[Callable[[], None]] = None
        self._sync_visibility(self.provider_combo.currentText())

    def set_on_back(self, callback: Callable[[], None]) -> None:
        self._on_back = callback

    def _handle_back(self) -> None:
        if self._on_back:
            self._on_back()

    def _sync_visibility(self, provider_name: str) -> None:
        is_openai = provider_name == "openai"
        self.openai_key.setEnabled(is_openai)
        self.openai_model.setEnabled(is_openai)
        self.ollama_base_url.setEnabled(not is_openai)
        self.ollama_model.setEnabled(not is_openai)

    def _combo_text(self, widget) -> str:
        """Get current text from a combo box or _LongTextWithHistory."""
        if isinstance(widget, _LongTextWithHistory):
            return widget.text()
        return (widget.currentText() or "").strip()

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
        override = self._parse_chunk_chars(self._combo_text(self.chunk_chars))
        if override is None:
            return base
        return Settings(
            upload_retries=base.upload_retries,
            json_repair_retries=base.json_repair_retries,
            translation_chunk_chars=override,
            local_metadata_chunk_chars=base.local_metadata_chunk_chars,
            local_metadata_first_chunks_with_title_author_hint=base.local_metadata_first_chunks_with_title_author_hint,
            max_chunk_summaries_for_summary_of_summaries=base.max_chunk_summaries_for_summary_of_summaries,
        )

    def build_config(self) -> LLMConfig:
        """Build LLMConfig from current UI fields."""
        provider_name = self.provider_combo.currentText().strip()
        if provider_name == "openai":
            api_key = self._combo_text(self.openai_key) or os.getenv(
                "OPENAI_API_KEY", ""
            )
            model = self._combo_text(self.openai_model) or "gpt-5-nano"
            if not api_key:
                raise ValueError(
                    "OpenAI API key is missing. Enter it or set OPENAI_API_KEY."
                )
            return OpenAIConfig(api_key=api_key, model=model)
        else:
            base_url = self._combo_text(self.ollama_base_url) or "http://localhost:11434"
            model = self._combo_text(self.ollama_model) or "llama3.1"
            return OllamaConfig(base_url=base_url, model=model)

    def _save_field_history(self) -> None:
        """Persist current field values to history."""
        provider = self.provider_combo.currentText().strip()
        values: dict[str, str] = {
            _FK_TARGET_LANG: self._combo_text(self.target_language),
            _FK_CHUNK_CHARS: self._combo_text(self.chunk_chars),
            _FK_SYS_CUSTOM: self._combo_text(self.system_prompt_customization),
            _FK_TRANS_INSTR: self._combo_text(self.translation_instruction),
        }
        if provider == "openai":
            values[_FK_OPENAI_KEY] = self._combo_text(self.openai_key)
            values[_FK_OPENAI_MODEL] = self._combo_text(self.openai_model)
        else:
            values[_FK_OLLAMA_URL] = self._combo_text(self.ollama_base_url)
            values[_FK_OLLAMA_MODEL] = self._combo_text(self.ollama_model)

        push_many(values)

    def _handle_continue(self) -> None:
        self.banner.hide()

        target_lang = self._combo_text(self.target_language)
        if not target_lang:
            self.banner.show_error("Please enter target language.")
            return

        try:
            settings = self._settings_with_optional_override()
        except Exception:
            self.banner.show_error(
                "Chunk size must be an integer between 200 and 200000."
            )
            return

        try:
            config = self.build_config()
            client = create_client(config)
            ConnectionService(client).test()
        except Exception as e:
            self.banner.show_error(str(e))
            return

        # Save all field values to history (after successful validation)
        self._save_field_history()

        sys_customization = self._combo_text(self.system_prompt_customization)
        trans_instruction = self._combo_text(self.translation_instruction)
        self._on_success(
            client, target_lang, settings, config,
            sys_customization, trans_instruction,
        )
