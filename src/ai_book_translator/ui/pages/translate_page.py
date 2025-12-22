from __future__ import annotations

from typing import Optional, Dict, Any, List

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QTextEdit,
    QProgressBar,
    QFileDialog,
)

from ai_book_translator.infrastructure.io.read_document.base import ReadDocument
from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.infrastructure.llm.base import LLMProvider

from ..widgets.error_banner import ErrorBanner
from ..workers.translation_worker import TranslationWorker


class TranslatePage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        self._on_back = on_back
        self._worker: Optional[TranslationWorker] = None
        self._paused = False

        # Will hold final translation payload from worker
        self._result: Optional[Dict[str, Any]] = None

        root = QVBoxLayout()
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel("Step 2 — Translation")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        self.banner = ErrorBanner()

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.stage = QLabel("")
        self.stage.setStyleSheet("color: #666;")

        self.output_preview = QTextEdit()
        self.output_preview.setReadOnly(True)
        self.output_preview.setPlaceholderText("Translation output will stream here…")

        controls = QHBoxLayout()

        btn_back = QPushButton("Back to input")
        btn_back.clicked.connect(self._on_back)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_pause.setEnabled(False)

        # ✅ NEW: download button
        self.btn_download = QPushButton("Download .txt")
        self.btn_download.clicked.connect(self._download_txt)
        self.btn_download.setEnabled(False)

        controls.addWidget(btn_back)
        controls.addStretch(1)
        controls.addWidget(self.btn_download)
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
        provider: LLMProvider,
        settings: Settings,
        document: DocumentInput,
        metadata_result: MetadataResult,
        target_language: str,
    ) -> None:
        self.banner.hide()
        self.progress.setValue(0)
        self.stage.setText("")
        self.output_preview.clear()

        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pause")
        self._paused = False

        self.btn_download.setEnabled(False)
        self._result = None

        if provider is None:
            self.banner.show_error("Provider is not configured.")
            return
        if document is None:
            self.banner.show_error("No document provided.")
            return
        if metadata_result is None:
            self.banner.show_error("No metadata available.")
            return

        # Ensure raw_text exists (extract if needed)
        if document.raw_text is None and document.file_path:
            try:
                raw = ReadDocument.from_path(document.file_path).read(
                    document.file_path
                )
                document = DocumentInput(file_path=document.file_path, raw_text=raw)
            except Exception as e:
                self.banner.show_error(f"Failed to extract text for translation: {e}")
                return

        self._worker = TranslationWorker(
            provider=provider,
            settings=settings,
            document=document,
            metadata_result=metadata_result,
            target_language=target_language,
        )
        self._worker.progressed.connect(self._on_progress)
        self._worker.chunk_done.connect(self._on_chunk_done)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

        self.btn_pause.setEnabled(True)

    def _on_progress(self, pct: int, stage: str) -> None:
        self.progress.setValue(pct)
        self.stage.setText(stage)

    def _on_chunk_done(self, idx: int, text: str) -> None:
        self.output_preview.append(text)
        self.output_preview.append("\n" + ("-" * 40) + "\n")

    def _on_success(self, obj: object) -> None:
        # Save payload for export
        if isinstance(obj, dict):
            self._result = obj  # contains "metadata", "target_language", "translations"
        else:
            self._result = None

        self.stage.setText("Translation complete.")
        self.btn_pause.setEnabled(False)
        self.btn_download.setEnabled(self._result is not None)

    def _on_fail(self, msg: str) -> None:
        self.banner.show_error(msg)
        self.btn_pause.setEnabled(False)
        self.btn_download.setEnabled(False)

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

    def _download_txt(self) -> None:
        if not self._result:
            self.banner.show_error("No translation available to export yet.")
            return

        meta = self._result.get("metadata") or {}
        target_language = self._result.get("target_language") or "Unknown"
        translations: List[Dict[str, str]] = self._result.get("translations") or []

        # Suggest a filename
        title = meta.get("title") if isinstance(meta, dict) else None
        title = (
            title
            if isinstance(title, str) and title.strip() and title != "not provided"
            else "translation"
        )
        suggested = f"{title} ({target_language}).txt"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save translation as .txt",
            suggested,
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        # Build file content
        lines: List[str] = []
        if isinstance(meta, dict):
            lines.append(f"Title: {meta.get('title', 'not provided')}")
            lines.append(f"Author(s): {meta.get('author(s)', 'not provided')}")
            lines.append(f"Source language: {meta.get('language', 'not provided')}")
        lines.append(f"Target language: {target_language}")
        lines.append("")
        lines.append("=" * 80)
        lines.append("")

        last_chapter = None
        for item in translations:
            ch = item.get("chapter") if isinstance(item, dict) else None
            tr = item.get("translation") if isinstance(item, dict) else None
            if isinstance(ch, str) and ch.strip() and ch != last_chapter:
                lines.append(f"\n## {ch.strip()}\n")
                last_chapter = ch.strip()
            if isinstance(tr, str) and tr.strip():
                lines.append(tr.strip())
                lines.append("")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines).strip() + "\n")
        except Exception as e:
            self.banner.show_error(f"Failed to save file: {e}")
            return

        self.banner.show_info(f"Saved: {path}")
