from __future__ import annotations

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar


class ProgressWidget(QWidget):
    def __init__(self, title: str = "Working..."):
        super().__init__()
        self._title = QLabel(title)
        self._title.setStyleSheet("font-size: 18px; font-weight: 600;")

        self._stage = QLabel("")
        self._stage.setStyleSheet("color: #666;")
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)

        layout = QVBoxLayout()
        layout.addWidget(self._title)
        layout.addWidget(self._stage)
        layout.addWidget(self._bar)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def set_stage(self, text: str) -> None:
        self._stage.setText(text)

    def set_progress(self, pct: int) -> None:
        self._bar.setValue(max(0, min(100, int(pct))))
