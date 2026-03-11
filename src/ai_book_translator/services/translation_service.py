from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput
from ai_book_translator.domain.translation_checkpoint import TranslationCheckpoint
from ai_book_translator.infrastructure.llm.client import LLMClient
from ai_book_translator.services.chunking import chunk_by_chars
from ai_book_translator.services.llm_json_client import LLMJsonClient
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
from ai_book_translator.infrastructure.persistence.metadata_cache import (
    find_metadata_cache_by_hash,
    load_metadata_cache,
)


ProgressCallback = Callable[[int, str], None]
ChunkDoneCallback = Callable[[int, str], None]
IsPausedCallback = Callable[[], bool]


class TranslationService:
    """Owns the complete translation workflow.

    Extracted from TranslationWorker so business logic is testable
    without Qt/threading dependencies.
    """

    def __init__(self, client: LLMClient, settings: Settings):
        self._client = client
        self._json_client = LLMJsonClient(client, settings.json_repair_retries)
        self._settings = settings

    def translate(
        self,
        document: DocumentInput,
        metadata: Dict[str, Any],
        target_language: str,
        output_path: str,
        *,
        llm_config_dict: Optional[Dict[str, Any]] = None,
        resume_checkpoint: Optional[TranslationCheckpoint] = None,
        resume_state_path: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
        on_chunk_done: Optional[ChunkDoneCallback] = None,
        is_paused: Optional[IsPausedCallback] = None,
    ) -> Dict[str, Any]:
        if document.raw_text is None:
            raise RuntimeError(
                "No raw_text available for translation. "
                "Ensure PDF/TXT extraction ran first."
            )

        raw_text = document.raw_text
        doc_hash = compute_document_hash(raw_text)

        chunks = chunk_by_chars(raw_text, self._settings.translation_chunk_chars)
        total = max(1, len(chunks))

        # --- Resolve metadata (prefer disk cache) ---
        meta = self._resolve_metadata(doc_hash, metadata)

        opt_ctx: Dict[str, Any] = {}
        for k in ["author(s)", "title", "summary", "chapters", "language"]:
            val = meta.get(k)
            if val and val != "not provided":
                opt_ctx[k] = val

        # Extract source languages for secondary language handling
        source_languages: Optional[List[str]] = None
        raw_lang = meta.get("language")
        if isinstance(raw_lang, list) and raw_lang and raw_lang != ["not provided"]:
            source_languages = raw_lang
        elif isinstance(raw_lang, str) and raw_lang != "not provided":
            source_languages = [raw_lang]

        # --- Resume defaults ---
        start_index = 0
        current_chapter: Optional[str] = None
        prev_tail = ""

        # Initialize current_chapter from first chapter key if starting fresh
        if not resume_checkpoint:
            chapters_map = meta.get("chapters")
            if isinstance(chapters_map, dict) and chapters_map:
                current_chapter = next(iter(chapters_map))

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine state path
        if resume_state_path:
            state_path = Path(resume_state_path)
        else:
            title = meta.get("title")
            state_path = make_state_path(
                title=title if isinstance(title, str) else None,
                doc_hash=doc_hash,
            )

        meta_path = find_metadata_cache_by_hash(doc_hash)

        # Apply resume checkpoint if present and matching
        if resume_checkpoint and resume_checkpoint.document_hash == doc_hash:
            start_index = resume_checkpoint.next_chunk_index
            ch0 = resume_checkpoint.current_chapter
            current_chapter = ch0 if ch0 and ch0.strip() else current_chapter
            prev_tail = resume_checkpoint.previous_tail or ""

            p0 = resume_checkpoint.output_txt_path
            if p0 and p0.strip():
                out_path = Path(p0)
                out_path.parent.mkdir(parents=True, exist_ok=True)

        # Save preflight checkpoint
        checkpoint = TranslationCheckpoint(
            document_hash=doc_hash,
            document_path=str(Path(document.file_path).resolve()) if document.file_path else "",
            target_language=target_language,
            next_chunk_index=start_index,
            chunks_total=total,
            current_chapter=current_chapter or "",
            previous_tail=prev_tail,
            output_txt_path=str(out_path),
            metadata_path=str(meta_path) if meta_path else "",
            translation_chunk_chars=self._settings.translation_chunk_chars,
            llm_config=llm_config_dict or {},
        )
        save_state(state_path, checkpoint.to_dict())

        # --- Translation loop ---
        with open(out_path, "a", encoding="utf-8") as fp:
            self._write_header_if_needed(fp, out_path, meta, target_language)

            if start_index > 0 and on_progress:
                on_progress(
                    int((start_index / total) * 100),
                    f"Resuming from chunk {start_index + 1}/{total}…",
                )

            for i in range(start_index, len(chunks)):
                # Pause support
                if is_paused:
                    while is_paused():
                        time.sleep(0.15)

                pct = int(((i + 1) / total) * 100)
                if on_progress:
                    on_progress(pct, f"Translating chunk {i + 1}/{total}…")

                chunk = chunks[i]

                sys_prompt = build_translation_system_prompt(
                    prev_tail, source_languages=source_languages
                )
                usr_prompt = build_translation_user_prompt(
                    chunk_text=chunk,
                    target_language=target_language,
                    current_chapter=current_chapter,
                    context=opt_ctx,
                )

                obj = self._json_client.generate_json_text_only(
                    system_prompt=sys_prompt,
                    user_prompt=usr_prompt,
                )

                ch = obj.get("chapter")
                tr = obj.get("translation")

                if not isinstance(tr, str) or not tr.strip():
                    raise RuntimeError(
                        f"Model returned empty translation for chunk {i}."
                    )

                if isinstance(ch, str) and ch.strip():
                    current_chapter = ch.strip()

                # Commit: append to output
                fp.write(tr.strip())
                fp.write("\n")
                fp.flush()

                prev_tail = chunk[-300:] if len(chunk) > 300 else chunk

                # Persist checkpoint atomically
                checkpoint = TranslationCheckpoint(
                    document_hash=doc_hash,
                    document_path=str(Path(document.file_path).resolve()) if document.file_path else "",
                    target_language=target_language,
                    next_chunk_index=i + 1,
                    chunks_total=total,
                    current_chapter=current_chapter or "",
                    previous_tail=prev_tail,
                    output_txt_path=str(out_path),
                    metadata_path=str(meta_path) if meta_path else "",
                    translation_chunk_chars=self._settings.translation_chunk_chars,
                    llm_config=llm_config_dict or {},
                )
                save_state(state_path, checkpoint.to_dict())

                if on_chunk_done:
                    on_chunk_done(i, tr)

        # Completed successfully — remove checkpoint
        delete_state(state_path)

        if on_progress:
            on_progress(100, "Done")

        return {"ok": True, "output_txt_path": str(out_path)}

    # ---- helpers ----

    def _resolve_metadata(
        self, doc_hash: str, fallback_meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        meta_path = find_metadata_cache_by_hash(doc_hash)
        if meta_path:
            try:
                record = load_metadata_cache(meta_path)
                if record and record.metadata:
                    return dict(record.metadata)
            except Exception:
                pass
        return dict(fallback_meta or {})

    @staticmethod
    def _write_header_if_needed(
        fp, out_path: Path, meta: Dict[str, Any], target_language: str
    ) -> None:
        try:
            is_empty = fp.tell() == 0 and out_path.stat().st_size == 0
        except Exception:
            is_empty = fp.tell() == 0

        if not is_empty:
            return

        lines: List[str] = []
        lines.append(f"Title: {meta.get('title', 'not provided')}")
        lines.append(f"Author(s): {meta.get('author(s)', 'not provided')}")
        lang = meta.get("language", ["not provided"])
        if isinstance(lang, list):
            lines.append(f"Source language(s): {', '.join(lang)}")
        else:
            lines.append(f"Source language(s): {lang}")
        lines.append(f"Translated to: {target_language}")
        lines.append("")
        lines.append("=" * 80)
        lines.append("")
        fp.write("\n".join(lines))
