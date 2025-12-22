from __future__ import annotations

from typing import Callable
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFileDialog,
    QTextEdit, QRadioButton, QButtonGroup, QGroupBox
)

from ai_book_translator.domain.models import DocumentInput
from ..widgets.error_banner import ErrorBanner


class BookInputPage(QWidget):
    def __init__(self, on_next: Callable[[DocumentInput], None], on_back: Callable[[], None]):
        super().__init__()
        self._on_next = on_next
        self._on_back = on_back

        self.banner = ErrorBanner()

        root = QVBoxLayout()
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel("Step 1 — Book input")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        self.radio_file = QRadioButton("Upload PDF/TXT")
        self.radio_paste = QRadioButton("Paste text")
        self.radio_file.setChecked(True)
        bg = QButtonGroup(self)
        bg.addButton(self.radio_file)
        bg.addButton(self.radio_paste)
        self.radio_file.toggled.connect(self._sync)

        file_box = QGroupBox("File")
        self.btn_choose = QPushButton("Choose PDF/TXT…")
        self.btn_choose.clicked.connect(self._choose_file)
        self.lbl_file = QLabel("No file selected")
        self.lbl_file.setStyleSheet("color: #666;")
        fb = QVBoxLayout()
        fb.addWidget(self.btn_choose)
        fb.addWidget(self.lbl_file)
        file_box.setLayout(fb)

        paste_box = QGroupBox("Paste text")
        self.txt = QTextEdit()
        self.txt.setPlaceholderText("Paste book text here…")
        pb = QVBoxLayout()
        pb.addWidget(self.txt)
        paste_box.setLayout(pb)

        self._selected_path: str | None = None

        nav = QHBoxLayout()
        btn_back = QPushButton("Back")
        btn_back.clicked.connect(self._on_back)
        btn_next = QPushButton("Next")
        btn_next.clicked.connect(self._next)

        nav.addWidget(btn_back)
        nav.addStretch(1)
        nav.addWidget(btn_next)

        root.addWidget(title)
        root.addWidget(self.banner)
        root.addWidget(self.radio_file)
        root.addWidget(file_box)
        root.addWidget(self.radio_paste)
        root.addWidget(paste_box)
        root.addStretch(1)
        root.addLayout(nav)

        self.setLayout(root)
        self._sync()

    def _sync(self) -> None:
        use_file = self.radio_file.isChecked()
        self.btn_choose.setEnabled(use_file)
        self.txt.setEnabled(not use_file)

    def _choose_file(self) -> None:
        self.banner.hide()
        fn, _ = QFileDialog.getOpenFileName(self, "Select book file", "", "Documents (*.pdf *.txt)")
        if not fn:
            return
        self._selected_path = fn
        self.lbl_file.setText(Path(fn).name)

    def _next(self) -> None:
        self.banner.hide()
        if self.radio_file.isChecked():
            if not self._selected_path:
                self.banner.show_error("Please choose a PDF or TXT file.")
                return
            self._on_next(DocumentInput(file_path=self._selected_path, raw_text=None))
        else:
            text = self.txt.toPlainText().strip()
            if not text:
                self.banner.show_error("Please paste some text.")
                return
            self._on_next(DocumentInput(file_path=None, raw_text=text))
