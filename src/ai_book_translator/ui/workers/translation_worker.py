from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput, MetadataResult
from ai_book_translator.infrastructure.llm.base import LLMProvider
from ai_book_translator.services.chunking import chunk_by_chars
from ai_book_translator.services.llm_json import chat_json_strict_with_repair
from ai_book_translator.services.prompts import (
    build_translation_system_prompt,
    build_translation_user_prompt,
)

from ai_book_translator.infrastructure.persistence.translation_state import (
    compute_document_hash,
    make_state_path,
    save_state,
    delete_state,
)


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
        output_txt_path: str,
        resume_state: Optional[Dict[str, Any]] = None,
        resume_state_path: Optional[str] = None,
    ):
        super().__init__()
        self.provider = provider
        self.settings = settings
        self.document = document
        self.metadata_result = metadata_result
        self.target_language = target_language
        self.output_txt_path = output_txt_path
        self.resume_state = resume_state or None
        self.resume_state_path = resume_state_path or None
        self._pause = False

    def request_pause(self) -> None:
        self._pause = True

    def request_resume(self) -> None:
        self._pause = False

    def _write_header_if_needed(
        self, fp, meta: Dict[str, Any], target_language: str
    ) -> None:
        # Only write header if file is empty.
        try:
            is_empty = fp.tell() == 0 and Path(self.output_txt_path).stat().st_size == 0
        except Exception:
            is_empty = fp.tell() == 0

        if not is_empty:
            return

        lines: List[str] = []
        lines.append(f"Title: {meta.get('title', 'not provided')}")
        lines.append(f"Author(s): {meta.get('author(s)', 'not provided')}")
        lines.append(f"Source language: {meta.get('language', 'not provided')}")
        lines.append(f"Translated to: {target_language}")
        lines.append("")
        lines.append("=" * 80)
        lines.append("")
        fp.write("\n".join(lines))

    def run(self) -> None:
        try:
            if self.document.raw_text is None:
                raise RuntimeError(
                    "No raw_text available for translation. Ensure PDF/TXT extraction is implemented."
                )

            raw_text = self.document.raw_text
            doc_hash = compute_document_hash(raw_text)

            chunks = chunk_by_chars(raw_text, self.settings.translation_chunk_chars)
            total = max(1, len(chunks))

            from ai_book_translator.infrastructure.persistence.metadata_cache import (
                find_metadata_cache_by_hash,
                load_metadata_cache,
            )

            # 1. Resolve metadata source (always prefer disk cache)
            meta_path = find_metadata_cache_by_hash(doc_hash)
            meta = {}
            if meta_path:
                try:
                    record = load_metadata_cache(meta_path)
                    if record and record.metadata:
                        meta = dict(record.metadata)
                except Exception:
                    # Fallback to in-memory if disk load fails
                    meta = dict(self.metadata_result.metadata or {})
            else:
                 meta = dict(self.metadata_result.metadata or {})

            # Use all available metadata as context
            opt_ctx: Dict[str, Any] = {}
            for k in ["author(s)", "title", "summary", "chapters"]:
                val = meta.get(k)
                if val and val != "not provided":
                    opt_ctx[k] = val

            # Resume defaults
            start_index = 0
            current_chapter: Optional[str] = None
            prev_tail = ""
            
            # --- IMPROVEMENT: Initialize current_chapter if starting fresh ---
            if not self.resume_state:
                 chapters_map = meta.get("chapters")
                 if isinstance(chapters_map, dict) and chapters_map:
                     # Pick the very first key as the starting chapter
                     current_chapter = next(iter(chapters_map))
            # -----------------------------------------------------------------

            # Prepare output path early (needed for preflight state object)
            out_path = Path(self.output_txt_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # Determine state path
            if self.resume_state_path:
                state_path = Path(self.resume_state_path)
            else:
                title = meta.get("title")
                state_path = make_state_path(
                    title=title if isinstance(title, str) else None,
                    doc_hash=doc_hash,
                )

            # If resume state exists and matches this document, apply it
            if self.resume_state and isinstance(self.resume_state, dict):
                if self.resume_state.get("document_hash") == doc_hash:
                    try:
                        start_index = int(
                            self.resume_state.get("current_chunk_index") or 0
                        )
                    except Exception:
                        start_index = 0

                    ch0 = self.resume_state.get("current_chapter")
                    current_chapter = (
                        ch0 if isinstance(ch0, str) and ch0.strip() else None
                    )

                    t0 = self.resume_state.get("last_translation_tail")
                    prev_tail = t0 if isinstance(t0, str) else ""

                    # Prefer the previously used output path if it exists in state
                    p0 = self.resume_state.get("output_txt_path")
                    if isinstance(p0, str) and p0.strip():
                        out_path = Path(p0)
                        out_path.parent.mkdir(parents=True, exist_ok=True)

            # Save a preflight state so resume works even if chunk 0 fails
            preflight_state: Dict[str, Any] = {
                "document_hash": doc_hash,
                "output_txt_path": str(out_path),
                "current_chunk_index": start_index,  # next chunk to translate
                "chunks_total": total,
                "current_chapter": current_chapter or "",
                "last_translation_tail": prev_tail or "",
                "metadata_path": str(meta_path) if meta_path else "",
                "target_language": self.target_language,
                "translation_chunk_chars": int(self.settings.translation_chunk_chars),
                "updated_at_unix": int(time.time()),
            }
            save_state(state_path, preflight_state)

            # Open output file in append mode (always incremental)
            with open(out_path, "a", encoding="utf-8") as fp:
                self._write_header_if_needed(fp, meta, self.target_language)

                if start_index > 0:
                    self.progressed.emit(
                        int((start_index / total) * 100),
                        f"Resuming from chunk {start_index + 1}/{total}…",
                    )

                for i in range(start_index, len(chunks)):
                    while self._pause:
                        self.msleep(150)

                    pct = int(((i + 1) / total) * 100)
                    self.progressed.emit(pct, f"Translating chunk {i+1}/{total}…")

                    chunk = chunks[i]

                    sys = build_translation_system_prompt(prev_tail)
                    usr = build_translation_user_prompt(
                        chunk_text=chunk,
                        target_language=self.target_language,
                        current_chapter=current_chapter,
                        context=opt_ctx,
                    )

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

                    # Append to output TXT immediately
                    fp.write(tr.strip())
                    fp.write("\n")
                    fp.flush()

                    prev_tail = tr[-300:] if len(tr) > 300 else tr

                    # Persist state after each successful chunk
                    state_obj: Dict[str, Any] = {
                        "document_hash": doc_hash,
                        "output_txt_path": str(out_path),
                        "current_chunk_index": i + 1,  # NEXT chunk to translate
                        "chunks_total": total,
                        "current_chapter": current_chapter or "",
                        "last_translation_tail": prev_tail,
                        "metadata_path": str(meta_path) if meta_path else "",
                        "target_language": self.target_language,
                        "translation_chunk_chars": int(
                            self.settings.translation_chunk_chars
                        ),
                        "updated_at_unix": int(time.time()),
                    }
                    save_state(state_path, state_obj)

                    self.chunk_done.emit(i, tr)

            # Completed successfully -> delete state JSON
            delete_state(state_path)

            self.progressed.emit(100, "Done")
            self.succeeded.emit({"ok": True, "output_txt_path": str(out_path)})

        except Exception as e:
            self.failed.emit(str(e))
