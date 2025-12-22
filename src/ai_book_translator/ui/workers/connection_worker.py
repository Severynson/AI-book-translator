from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from ai_book_translator.infrastructure.llm.base import LLMProvider
from ai_book_translator.services.connection_service import ConnectionService


class ConnectionWorker(QThread):
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, provider: LLMProvider):
        super().__init__()
        self.provider = provider

    def run(self) -> None:
        try:
            ConnectionService(self.provider).test()
            self.succeeded.emit()
        except Exception as e:
            self.failed.emit(str(e))
