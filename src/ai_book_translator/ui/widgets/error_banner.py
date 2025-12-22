from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QPushButton


class ErrorBanner(QWidget):
    def __init__(self):
        super().__init__()
        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._close = QPushButton("×")
        self._close.setFixedWidth(32)
        self._close.clicked.connect(self.hide)

        layout = QHBoxLayout()
        layout.addWidget(self._label, 1)
        layout.addWidget(self._close, 0)
        layout.setContentsMargins(10, 8, 10, 8)
        self.setLayout(layout)

        self.setStyleSheet("""
            QWidget {
                background: #3b1c1c;
                border: 1px solid #7a2b2b;
                border-radius: 8px;
                color: #ffd7d7;
            }
            QPushButton {
                background: transparent;
                border: none;
                font-size: 18px;
                color: #ffd7d7;
            }
            QPushButton:hover { color: white; }
        """)
        self.hide()

    def show_error(self, message: str) -> None:
        self._label.setText(message)
        self.show()
