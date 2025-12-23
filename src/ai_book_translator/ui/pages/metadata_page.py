from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QTextEdit,
)

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.infrastructure.llm.base import LLMProvider

from ..widgets.error_banner import ErrorBanner
from ..widgets.progress_widget import ProgressWidget
from ..workers.metadata_worker import MetadataWorker


class MetadataPage(QWidget):
    def __init__(
        self, on_done: Callable[[MetadataResult], None], on_back: Callable[[], None]
    ):
        super().__init__()
        self._on_done = on_done
        self._on_back = on_back
        self._worker: Optional[MetadataWorker] = None
        self._last_result: Optional[MetadataResult] = None

        root = QVBoxLayout()
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel("Step 1 — Metadata extraction")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        self.banner = ErrorBanner()
        self.progress = ProgressWidget("Generating metadata JSON…")

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Metadata JSON will appear here when ready…")

        nav = QHBoxLayout()
        btn_back = QPushButton("Back")
        btn_back.clicked.connect(self._on_back)
        self.btn_continue = QPushButton("Continue")
        self.btn_continue.setEnabled(False)
        self.btn_continue.clicked.connect(self._continue)

        nav.addWidget(btn_back)
        nav.addStretch(1)
        nav.addWidget(self.btn_continue)

        root.addWidget(title)
        root.addWidget(self.banner)
        root.addWidget(self.progress)
        root.addWidget(self.preview, 1)
        root.addLayout(nav)

        self.setLayout(root)

    def start(
        self,
        provider: LLMProvider,
        settings: Settings,
        document: DocumentInput,
        target_language: str,
    ) -> None:
        self.banner.hide()
        self.progress.set_progress(0)
        self.progress.set_stage("")
        self.preview.clear()
        self.btn_continue.setEnabled(False)
        self._last_result = None

        if provider is None:
            self.banner.show_error("Provider is not configured.")
            return
        if document is None:
            self.banner.show_error("No document provided.")
            return

        display_name = ""
        if document.file_path:
            display_name = str(document.file_path)
        else:
            display_name = "pasted text"

        self._worker = MetadataWorker(
            provider=provider,
            settings=settings,
            document=document,
            target_language=target_language,
            display_name=display_name,
        )
        self._worker.progressed.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_progress(self, pct: int, stage: str) -> None:
        self.progress.set_progress(pct)
        self.progress.set_stage(stage)

    def _on_success(self, res: MetadataResult) -> None:
        import json

        self._last_result = res
        self.preview.setPlainText(
            json.dumps(res.metadata, ensure_ascii=False, indent=2)
        )
        self.btn_continue.setEnabled(True)

    def _on_fail(self, msg: str) -> None:
        self.banner.show_error(msg)

    def _continue(self) -> None:
        if self._last_result is not None:
            self._on_done(self._last_result)
