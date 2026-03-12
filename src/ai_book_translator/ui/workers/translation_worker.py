from __future__ import annotations

import json
from typing import Any, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.domain.translation_checkpoint import TranslationCheckpoint
from ai_book_translator.infrastructure.llm.client import LLMClient
from ai_book_translator.services.translation_service import (
    TranslationService,
    ErrorPopupPayload,
)


class TranslationWorker(QThread):
    """Thin Qt wrapper around TranslationService.

    All business logic lives in TranslationService; this class only
    bridges Qt signals/threading with service callbacks.
    """

    progressed = pyqtSignal(int, str)
    chunk_done = pyqtSignal(int, str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    # Error popup signal: sends JSON-serialized ErrorPopupPayload
    error_popup_requested = pyqtSignal(str)

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
        system_prompt_customization: str = "",
        translation_instruction: str = "",
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
        self._system_prompt_customization = system_prompt_customization
        self._translation_instruction = translation_instruction
        self._pause = False

        # Mutex for error popup synchronization
        self._popup_mutex = QMutex()
        self._popup_condition = QWaitCondition()
        self._popup_response: Optional[str] = None

    def request_pause(self) -> None:
        self._pause = True

    def request_resume(self) -> None:
        self._pause = False

    def submit_popup_response(self, response: Optional[str]) -> None:
        """Called from UI thread when user responds to error popup."""
        self._popup_mutex.lock()
        self._popup_response = response
        self._popup_condition.wakeAll()
        self._popup_mutex.unlock()

    def _handle_error_popup(self, payload: ErrorPopupPayload) -> Optional[str]:
        """Bridge between TranslationService callback and Qt signal.

        Emits signal, then blocks this worker thread until UI responds.
        """
        # Serialize payload for signal
        payload_json = json.dumps({
            "chunk_index": payload.chunk_index,
            "original_error": payload.original_error,
            "error_category": payload.error_category,
            "user_explanation": payload.user_explanation,
            "likely_cause": payload.likely_cause,
            "suggest_prompt_patch": payload.suggest_prompt_patch,
            "confidence_can_be_fixed_with_prompt": payload.confidence_can_be_fixed_with_prompt,
        })

        self._popup_mutex.lock()
        self._popup_response = None
        self._popup_mutex.unlock()

        # Emit signal to UI thread
        self.error_popup_requested.emit(payload_json)

        # Wait for UI response
        self._popup_mutex.lock()
        while self._popup_response is None:
            self._popup_condition.wait(self._popup_mutex)
        response = self._popup_response
        self._popup_mutex.unlock()

        # Empty string means user rejected
        return response if response else None

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
                system_prompt_customization=self._system_prompt_customization,
                translation_instruction=self._translation_instruction,
                on_progress=lambda pct, msg: self.progressed.emit(pct, msg),
                on_chunk_done=lambda idx, text: self.chunk_done.emit(idx, text),
                is_paused=lambda: self._pause,
                on_error_popup=self._handle_error_popup,
            )
            self.succeeded.emit(result)
        except Exception as e:
            self.failed.emit(str(e))
