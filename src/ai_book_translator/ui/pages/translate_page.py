from __future__ import annotations

import json
from typing import Optional, Dict, Any

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QTextEdit,
    QProgressBar,
    QFileDialog,
    QMessageBox,
    QInputDialog,
)

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.domain.translation_checkpoint import TranslationCheckpoint
from ai_book_translator.infrastructure.llm.client import LLMClient
from ai_book_translator.services.document_service import ensure_raw_text

from ..widgets.error_banner import ErrorBanner
from ..workers.translation_worker import TranslationWorker


class TranslatePage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        self._on_back = on_back
        self._worker: Optional[TranslationWorker] = None
        self._paused = False

        root = QVBoxLayout()
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel("Step 4 — Translation")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        self.banner = ErrorBanner()

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.stage = QLabel("")
        self.stage.setStyleSheet("color: #666;")

        self.output_preview = QTextEdit()
        self.output_preview.setReadOnly(True)
        self.output_preview.setPlaceholderText("Translation output will stream here...")

        controls = QHBoxLayout()

        btn_back = QPushButton("Back to input")
        btn_back.clicked.connect(self._on_back)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_pause.setEnabled(False)

        controls.addWidget(btn_back)
        controls.addStretch(1)
        controls.addWidget(self.btn_pause)

        root.addWidget(title)
        root.addWidget(self.banner)
        root.addWidget(self.progress)
        root.addWidget(self.stage)
        root.addWidget(self.output_preview, 1)
        root.addLayout(controls)

        self.setLayout(root)

    def start(
        self,
        client: LLMClient,
        settings: Settings,
        document: DocumentInput,
        metadata_result: MetadataResult,
        target_language: str,
        resume_checkpoint: Optional[TranslationCheckpoint] = None,
        resume_state_path: Optional[str] = None,
        llm_config_dict: Optional[Dict[str, Any]] = None,
        system_prompt_customization: str = "",
        translation_instruction: str = "",
    ) -> None:
        self.banner.hide()
        self.progress.setValue(0)
        self.stage.setText("")
        self.output_preview.clear()

        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pause")
        self._paused = False

        if client is None:
            self.banner.show_error("Provider is not configured.")
            return
        if document is None:
            self.banner.show_error("No document provided.")
            return
        if metadata_result is None:
            self.banner.show_error("No metadata available.")
            return

        # Ensure raw_text exists
        if document.raw_text is None and document.file_path:
            try:
                document = ensure_raw_text(document)
            except Exception as e:
                self.banner.show_error(f"Failed to extract text for translation: {e}")
                return

        # Decide output path
        output_txt_path = None
        if resume_checkpoint:
            output_txt_path = resume_checkpoint.output_txt_path or None

        if not output_txt_path:
            meta = metadata_result.metadata or {}
            title = meta.get("title") if isinstance(meta, dict) else None
            if (
                not isinstance(title, str)
                or not title.strip()
                or title == "not provided"
            ):
                title = "translation"
            suggested = f"{title} ({target_language}).txt"

            path, _ = QFileDialog.getSaveFileName(
                self,
                "Choose where to save the translation (.txt will be written continuously)",
                suggested,
                "Text files (*.txt);;All files (*)",
            )
            if not path:
                self.banner.show_error(
                    "Translation cancelled: no output path selected."
                )
                return
            output_txt_path = path

        self._worker = TranslationWorker(
            client=client,
            settings=settings,
            document=document,
            metadata_result=metadata_result,
            target_language=target_language,
            output_txt_path=str(output_txt_path),
            resume_checkpoint=resume_checkpoint,
            resume_state_path=resume_state_path,
            llm_config_dict=llm_config_dict,
            system_prompt_customization=system_prompt_customization,
            translation_instruction=translation_instruction,
        )
        self._worker.progressed.connect(self._on_progress)
        self._worker.chunk_done.connect(self._on_chunk_done)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_fail)
        self._worker.error_popup_requested.connect(self._on_error_popup)
        self._worker.start()

        self.btn_pause.setEnabled(True)

    def _on_progress(self, pct: int, stage: str) -> None:
        self.progress.setValue(pct)
        self.stage.setText(stage)

    def _on_chunk_done(self, idx: int, text: str) -> None:
        self.output_preview.append(text)
        self.output_preview.append("\n" + ("-" * 40) + "\n")

    def _on_success(self, _obj: object) -> None:
        self.stage.setText("Translation complete.")
        self.btn_pause.setEnabled(False)

    def _on_fail(self, msg: str) -> None:
        self.banner.show_error(msg)
        self.btn_pause.setEnabled(False)

    def _on_error_popup(self, payload_json: str) -> None:
        """Handle LLM-assisted error popup from worker thread."""
        try:
            payload = json.loads(payload_json)
        except Exception:
            if self._worker:
                self._worker.submit_popup_response("")
            return

        explanation = payload.get("user_explanation", "Unknown error")
        likely_cause = payload.get("likely_cause", "")
        suggested_patch = payload.get("suggest_prompt_patch", "")
        confidence = payload.get("confidence_can_be_fixed_with_prompt", False)

        detail_text = f"Error: {payload.get('original_error', '')}\n\n"
        if likely_cause:
            detail_text += f"Likely cause: {likely_cause}\n\n"
        if suggested_patch:
            detail_text += f"Suggested prompt addition:\n{suggested_patch}\n"

        if confidence and suggested_patch:
            msg = QMessageBox(self)
            msg.setWindowTitle("Translation Error — Possible Fix")
            msg.setText(explanation)
            msg.setDetailedText(detail_text)
            btn_approve = msg.addButton("Apply suggested fix", QMessageBox.AcceptRole)
            btn_edit = msg.addButton("Edit fix", QMessageBox.ActionRole)
            btn_reject = msg.addButton("Skip (abort chunk)", QMessageBox.RejectRole)
            msg.exec_()

            clicked = msg.clickedButton()
            if clicked == btn_approve:
                if self._worker:
                    self._worker.submit_popup_response(suggested_patch)
                return
            elif clicked == btn_edit:
                text, ok = QInputDialog.getMultiLineText(
                    self,
                    "Edit prompt patch",
                    "Enter custom prompt addition:",
                    suggested_patch,
                )
                if ok and text.strip():
                    if self._worker:
                        self._worker.submit_popup_response(text.strip())
                    return

        # Rejected or no fix available
        if self._worker:
            self._worker.submit_popup_response("")

    def _toggle_pause(self) -> None:
        if not self._worker:
            return
        if not self._paused:
            self._worker.request_pause()
            self._paused = True
            self.btn_pause.setText("Continue")
            self.stage.setText("Paused")
        else:
            self._worker.request_resume()
            self._paused = False
            self.btn_pause.setText("Pause")
