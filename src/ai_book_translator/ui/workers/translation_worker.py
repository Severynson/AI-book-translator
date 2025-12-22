from __future__ import annotations

from typing import Any, Dict, List

from PyQt5.QtCore import QThread, pyqtSignal

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.infrastructure.llm.base import LLMProvider
from ai_book_translator.services.chunking import chunk_by_chars
from ai_book_translator.services.llm_json import chat_json_strict_with_repair


class TranslationWorker(QThread):
    progressed = pyqtSignal(int, str)
    chunk_done = pyqtSignal(int, str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        provider: LLMProvider,
        settings: Settings,
        document: DocumentInput,
        metadata_result: MetadataResult,
        target_language: str,
    ):
        super().__init__()
        self.provider = provider
        self.settings = settings
        self.document = document
        self.metadata_result = metadata_result
        self.target_language = target_language
        self._pause = False

    def request_pause(self) -> None:
        self._pause = True

    def request_resume(self) -> None:
        self._pause = False

    def run(self) -> None:
        try:
            if self.document.raw_text is None:
                raise RuntimeError(
                    "No raw_text available for translation. Ensure PDF/TXT extraction is implemented."
                )

            chunks = chunk_by_chars(
                self.document.raw_text, self.settings.translation_chunk_chars
            )
            total = max(1, len(chunks))

            meta = dict(self.metadata_result.metadata or {})
            author = meta.get("author(s)")
            title = meta.get("title")
            opt_ctx: Dict[str, Any] = {}
            if author and author != "not provided":
                opt_ctx["author(s)"] = author
            if title and title != "not provided":
                opt_ctx["title"] = title

            current_chapter = None
            prev_tail = ""
            translations: List[Dict[str, str]] = []

            for i, chunk in enumerate(chunks):
                while self._pause:
                    self.msleep(150)

                pct = int((i / total) * 100)
                self.progressed.emit(pct, f"Translating chunk {i+1}/{total}…")

                sys = (
                    "You are a professional book translator. "
                    'Return STRICT JSON only: {"chapter": "...", "translation": "..."}. '
                    "No markdown. No commentary.\n\n"
                    f"Previous translation tail (last 300 chars):\n{prev_tail}"
                )

                ctx_block = f"Optional context: {opt_ctx}\n" if opt_ctx else ""

                usr = f"""
{ctx_block}Target language: {self.target_language}
Current chapter (from previous chunk, may overwrite if new chapter begins): {current_chapter}

Chunk text:
{chunk}

Output JSON only.
""".strip()

                obj = chat_json_strict_with_repair(
                    provider=self.provider,
                    system_prompt=sys,
                    user_prompt=usr,
                    repair_retries=2,
                )

                ch = obj.get("chapter")
                tr = obj.get("translation")
                if not isinstance(tr, str) or not tr.strip():
                    raise RuntimeError(
                        f"Model returned empty translation for chunk {i}."
                    )

                if isinstance(ch, str) and ch.strip():
                    current_chapter = ch.strip()

                prev_tail = tr[-300:] if len(tr) > 300 else tr
                translations.append(
                    {"chapter": current_chapter or "", "translation": tr}
                )
                self.chunk_done.emit(i, tr)

            self.progressed.emit(100, "Done")
            self.succeeded.emit(
                {
                    "metadata": meta,
                    "target_language": self.target_language,
                    "translations": translations,
                }
            )
        except Exception as e:
            self.failed.emit(str(e))
