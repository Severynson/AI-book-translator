from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.domain.translation_checkpoint import TranslationCheckpoint
from ai_book_translator.infrastructure.llm.client import LLMClient
from ai_book_translator.services.translation_service import TranslationService


class TranslationWorker(QThread):
    """Thin Qt wrapper around TranslationService.

    All business logic lives in TranslationService; this class only
    bridges Qt signals/threading with service callbacks.
    """

    progressed = pyqtSignal(int, str)
    chunk_done = pyqtSignal(int, str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        client: LLMClient,
        settings: Settings,
        document: DocumentInput,
        metadata_result: MetadataResult,
        target_language: str,
        output_txt_path: str,
        resume_checkpoint: Optional[TranslationCheckpoint] = None,
        resume_state_path: Optional[str] = None,
        llm_config_dict: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self._client = client
        self._settings = settings
        self._document = document
        self._metadata_result = metadata_result
        self._target_language = target_language
        self._output_txt_path = output_txt_path
        self._resume_checkpoint = resume_checkpoint
        self._resume_state_path = resume_state_path
        self._llm_config_dict = llm_config_dict
        self._pause = False

    def request_pause(self) -> None:
        self._pause = True

    def request_resume(self) -> None:
        self._pause = False

    def run(self) -> None:
        try:
            svc = TranslationService(self._client, self._settings)
            result = svc.translate(
                document=self._document,
                metadata=dict(self._metadata_result.metadata or {}),
                target_language=self._target_language,
                output_path=self._output_txt_path,
                llm_config_dict=self._llm_config_dict,
                resume_checkpoint=self._resume_checkpoint,
                resume_state_path=self._resume_state_path,
                on_progress=lambda pct, msg: self.progressed.emit(pct, msg),
                on_chunk_done=lambda idx, text: self.chunk_done.emit(idx, text),
                is_paused=lambda: self._pause,
            )
            self.succeeded.emit(result)
        except Exception as e:
            self.failed.emit(str(e))
