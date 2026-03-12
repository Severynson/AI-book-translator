from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput
from ai_book_translator.domain.translation_checkpoint import TranslationCheckpoint
from ai_book_translator.infrastructure.llm.client import LLMClient
from ai_book_translator.infrastructure.llm.exceptions import (
    classify_error,
    ErrorCategory,
    InvalidJSONError,
)
from ai_book_translator.services.chunking import chunk_by_chars
from ai_book_translator.services.llm_json_client import LLMJsonClient
from ai_book_translator.services.prompts import (
    build_translation_system_prompt,
    build_translation_user_prompt,
    find_matching_chapter_key,
    ERROR_EXPLANATION_SYSTEM_PROMPT,
    build_error_explanation_prompt,
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


@dataclass
class ErrorPopupPayload:
    """Structured payload for LLM-assisted error popup in UI."""
    chunk_index: int
    original_error: str
    error_category: str
    user_explanation: str = ""
    likely_cause: str = ""
    suggest_prompt_patch: str = ""
    confidence_can_be_fixed_with_prompt: bool = False


ErrorPopupCallback = Callable[[ErrorPopupPayload], Optional[str]]


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
        system_prompt_customization: str = "",
        translation_instruction: str = "",
        on_progress: Optional[ProgressCallback] = None,
        on_chunk_done: Optional[ChunkDoneCallback] = None,
        is_paused: Optional[IsPausedCallback] = None,
        on_error_popup: Optional[ErrorPopupCallback] = None,
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

        # Chapter metadata for fuzzy matching
        chapters_meta = meta.get("chapters")
        if not isinstance(chapters_meta, dict):
            chapters_meta = {}

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
        tail_status = "clean"
        last_tail_translation = ""
        boundary_repair_marker = "|||RETRANSLATE_PREVIOUS|||"

        # Initialize current_chapter from first chapter key if starting fresh
        if not resume_checkpoint:
            chapters_map = meta.get("chapters")
            if isinstance(chapters_map, dict) and chapters_map:
                current_chapter = next(iter(chapters_map))
        else:
            # Restore custom instructions from checkpoint
            if not system_prompt_customization:
                system_prompt_customization = resume_checkpoint.system_prompt_customization or ""
            if not translation_instruction:
                translation_instruction = resume_checkpoint.translation_instruction or ""
            boundary_repair_marker = resume_checkpoint.boundary_repair_marker or boundary_repair_marker

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
            tail_status = resume_checkpoint.last_committed_chunk_tail_status or "clean"
            last_tail_translation = resume_checkpoint.last_committed_chunk_tail_translation or ""

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
            system_prompt_customization=system_prompt_customization,
            translation_instruction=translation_instruction,
            boundary_repair_marker=boundary_repair_marker,
            last_committed_chunk_tail_translation=last_tail_translation,
            last_committed_chunk_tail_status=tail_status,
        )
        save_state(state_path, checkpoint.to_dict())

        # --- Translation loop ---
        with open(out_path, "a", encoding="utf-8") as fp:
            self._write_header_if_needed(fp, out_path, meta, target_language)

            if start_index > 0 and on_progress:
                on_progress(
                    int((start_index / total) * 100),
                    f"Resuming from chunk {start_index + 1}/{total}...",
                )

            for i in range(start_index, len(chunks)):
                # Pause support
                if is_paused:
                    while is_paused():
                        time.sleep(0.15)

                pct = int(((i + 1) / total) * 100)
                if on_progress:
                    on_progress(pct, f"Translating chunk {i + 1}/{total}...")

                chunk = chunks[i]

                sys_prompt = build_translation_system_prompt(
                    prev_tail,
                    source_languages=source_languages,
                    system_prompt_customization=system_prompt_customization,
                )
                usr_prompt = build_translation_user_prompt(
                    chunk_text=chunk,
                    target_language=target_language,
                    current_chapter=current_chapter,
                    context=opt_ctx,
                    translation_instruction=translation_instruction,
                )

                obj = self._generate_chunk_with_error_handling(
                    sys_prompt=sys_prompt,
                    usr_prompt=usr_prompt,
                    chunk_index=i,
                    system_prompt_customization=system_prompt_customization,
                    on_error_popup=on_error_popup,
                )

                ch = obj.get("chapter")
                tr = obj.get("translation")

                if not isinstance(tr, str) or not tr.strip():
                    raise RuntimeError(
                        f"Model returned empty translation for chunk {i}."
                    )

                if isinstance(ch, str) and ch.strip():
                    candidate = ch.strip()
                    # Trust the LLM's chapter detection. Use fuzzy matching to
                    # map back to a metadata key so the prompt loads the right
                    # detailed description for the next chunk.
                    matched = find_matching_chapter_key(candidate, chapters_meta)
                    current_chapter = matched if matched else candidate

                # --- Boundary repair logic ---
                repair_fragment = obj.get("repair_previous_fragment")
                repair_retranslation = obj.get("repair_retranslation")

                if (
                    isinstance(repair_fragment, str)
                    and repair_fragment.strip()
                    and isinstance(repair_retranslation, str)
                    and repair_retranslation.strip()
                    and last_tail_translation
                ):
                    self._apply_tail_repair(
                        fp, out_path, repair_fragment.strip(), repair_retranslation.strip()
                    )

                # Commit: append to output
                fp.write(tr.strip())
                fp.write("\n")
                fp.flush()

                # Track tail status
                chunk_tail_status = obj.get("tail_status", "clean")
                if chunk_tail_status not in ("clean", "possibly_truncated", "repaired"):
                    chunk_tail_status = "clean"
                tail_status = chunk_tail_status

                # Save last 300 chars of translated text for boundary repair context
                last_tail_translation = tr.strip()[-300:] if len(tr.strip()) > 300 else tr.strip()

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
                    system_prompt_customization=system_prompt_customization,
                    translation_instruction=translation_instruction,
                    boundary_repair_marker=boundary_repair_marker,
                    last_committed_chunk_tail_translation=last_tail_translation,
                    last_committed_chunk_tail_status=tail_status,
                )
                save_state(state_path, checkpoint.to_dict())

                if on_chunk_done:
                    on_chunk_done(i, tr)

        # Completed successfully - remove checkpoint
        delete_state(state_path)

        if on_progress:
            on_progress(100, "Done")

        return {"ok": True, "output_txt_path": str(out_path)}

    # ---- chunk generation with error handling ----

    def _generate_chunk_with_error_handling(
        self,
        sys_prompt: str,
        usr_prompt: str,
        chunk_index: int,
        system_prompt_customization: str,
        on_error_popup: Optional[ErrorPopupCallback],
    ) -> Dict[str, Any]:
        """Generate JSON for a chunk with error classification and optional LLM-assisted recovery."""
        try:
            return self._json_client.generate_json_text_only(
                system_prompt=sys_prompt,
                user_prompt=usr_prompt,
            )
        except Exception as exc:
            category = classify_error(exc)

            # Only offer LLM-assisted popup for prompt-fixable or invalid output errors
            if on_error_popup and category in (
                ErrorCategory.PROMPT_FIXABLE,
                ErrorCategory.INVALID_MODEL_OUTPUT,
            ):
                payload = self._build_error_popup(
                    exc, chunk_index, sys_prompt, system_prompt_customization
                )
                # Callback returns user-approved prompt patch (or None to abort)
                user_patch = on_error_popup(payload)
                if user_patch is not None:
                    # Retry with patched system prompt
                    patched_sys = sys_prompt + f"\n\n{user_patch}"
                    try:
                        return self._json_client.generate_json_text_only(
                            system_prompt=patched_sys,
                            user_prompt=usr_prompt,
                        )
                    except Exception:
                        pass  # Fall through to re-raise original

            raise

    def _build_error_popup(
        self,
        exc: Exception,
        chunk_index: int,
        sys_prompt: str,
        system_prompt_customization: str,
    ) -> ErrorPopupPayload:
        """Build error popup payload, optionally using LLM for explanation."""
        category = classify_error(exc)
        payload = ErrorPopupPayload(
            chunk_index=chunk_index,
            original_error=str(exc),
            error_category=category,
        )

        # Try getting LLM-assisted explanation
        try:
            explanation_prompt = build_error_explanation_prompt(
                error_message=str(exc),
                malformed_output_excerpt=str(exc)[:200],
                current_system_prompt_summary="book translation with JSON output",
                current_user_customization=system_prompt_customization,
            )
            obj = self._json_client.generate_json_text_only(
                system_prompt=ERROR_EXPLANATION_SYSTEM_PROMPT,
                user_prompt=explanation_prompt,
            )
            payload.user_explanation = str(obj.get("user_explanation", ""))
            payload.likely_cause = str(obj.get("likely_cause", ""))
            payload.suggest_prompt_patch = str(obj.get("suggest_prompt_patch", ""))
            payload.confidence_can_be_fixed_with_prompt = bool(
                obj.get("confidence_can_be_fixed_with_prompt", False)
            )
        except Exception:
            # LLM explanation failed; provide basic payload
            payload.user_explanation = str(exc)

        return payload

    # ---- boundary repair ----

    def _apply_tail_repair(
        self,
        fp,
        out_path: Path,
        old_fragment: str,
        new_fragment: str,
    ) -> None:
        """Replace the last occurrence of old_fragment in the output file with new_fragment."""
        fp.flush()
        try:
            content = out_path.read_text(encoding="utf-8")
            idx = content.rfind(old_fragment)
            if idx == -1:
                # Cannot find fragment - skip repair silently to avoid corruption
                return
            new_content = content[:idx] + new_fragment + content[idx + len(old_fragment):]
            out_path.write_text(new_content, encoding="utf-8")
            # Reopen at end for continued appending
            fp.seek(0, 2)
        except Exception:
            # Repair failed - skip to avoid corruption
            pass

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
