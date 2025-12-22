from __future__ import annotations
from typing import Any, List

from ..config.settings import Settings
from ..domain.models import DocumentInput, MetadataResult
from ..domain.schemas import validate_metadata_json, normalize_not_provided
from ..infrastructure.llm.base import LLMProvider
from ..infrastructure.llm.exceptions import (
    UploadNotSupportedError,
    UploadFailedError,
    TransientLLMError,
    DocumentReadError,
)
from ..infrastructure.llm.json_parser import parse_json_strict
from ..infrastructure.llm.exceptions import InvalidJSONError
from .chunking import chunk_by_chars
from .prompts import (
    METADATA_EXTRACTION_SYSTEM_PROMPT,
    METADATA_UPLOAD_USER_PROMPT,
    LOCAL_CHUNK_SUMMARY_SYSTEM_PROMPT,
    build_local_chunk_summary_user_prompt,
    SUMMARY_OF_SUMMARIES_SYSTEM_PROMPT,
    build_summary_of_summaries_user_prompt,
)
from .llm_json import chat_json_strict_with_repair


class MetadataService:
    def __init__(self, provider: LLMProvider, settings: Settings):
        self.provider = provider
        self.settings = settings

    def generate_metadata(self, doc: DocumentInput, target_language: str, **kwargs: Any) -> MetadataResult:
        # Attempt upload-first if file_path is provided
        if doc.file_path:
            try:
                meta = self._upload_metadata(doc.file_path, **kwargs)
                meta = normalize_not_provided(meta)
                validate_metadata_json(meta)
                meta["target_language"] = target_language
                return MetadataResult(metadata=meta, strategy_used="upload")

            except (UploadNotSupportedError, UploadFailedError) as e:
                return self._chunked_fallback(doc, target_language, reason=str(e), **kwargs)

            except TransientLLMError:
                for _ in range(self.settings.upload_retries):
                    try:
                        meta = self._upload_metadata(doc.file_path, **kwargs)
                        meta = normalize_not_provided(meta)
                        validate_metadata_json(meta)
                        meta["target_language"] = target_language
                        return MetadataResult(metadata=meta, strategy_used="upload")
                    except TransientLLMError:
                        continue
                    except (UploadNotSupportedError, UploadFailedError) as e:
                        return self._chunked_fallback(doc, target_language, reason=str(e), **kwargs)
                return self._chunked_fallback(doc, target_language, reason="upload transient failure", **kwargs)

        # No file_path => direct fallback (pasted text flow)
        return self._chunked_fallback(doc, target_language, reason="no file provided for upload", **kwargs)

    def _upload_metadata(self, file_path: str, **kwargs: Any) -> dict:
        system = METADATA_EXTRACTION_SYSTEM_PROMPT
        user = METADATA_UPLOAD_USER_PROMPT

        raw = self.provider.chat_text_with_document(
            system_prompt=system,
            user_prompt=user,
            file_path=file_path,
            **kwargs
        )

        # Parse strict; if formatting is bad, repair using a normal chat call (no re-upload)
        try:
            return parse_json_strict(raw)
        except InvalidJSONError:
            return chat_json_strict_with_repair(
                provider=self.provider,
                system_prompt=system,
                user_prompt=f"Rewrite the following as valid JSON only, matching the required schema:\n\n{raw}",
                repair_retries=self.settings.json_repair_retries,
                **kwargs
            )

    def _chunked_fallback(self, doc: DocumentInput, target_language: str, reason: str, **kwargs: Any) -> MetadataResult:
        if doc.raw_text is None:
            raise DocumentReadError("Chunked fallback requires raw_text (extract the document first).")

        chunks = chunk_by_chars(doc.raw_text, self.settings.local_metadata_chunk_chars)

        chunk_summaries: List[str] = []
        for i, ch in enumerate(chunks[: self.settings.max_chunk_summaries_for_summary_of_summaries]):
            is_early = i < self.settings.local_metadata_first_chunks_with_title_author_hint
            sys = LOCAL_CHUNK_SUMMARY_SYSTEM_PROMPT
            usr = build_local_chunk_summary_user_prompt(ch, is_early_chunk=is_early)
            s = self.provider.chat_text(system_prompt=sys, user_prompt=usr, **kwargs).strip()
            chunk_summaries.append(s)

        system = SUMMARY_OF_SUMMARIES_SYSTEM_PROMPT
        user = build_summary_of_summaries_user_prompt(chunk_summaries)

        meta = chat_json_strict_with_repair(
            provider=self.provider,
            system_prompt=system,
            user_prompt=user,
            repair_retries=self.settings.json_repair_retries,
            **kwargs
        )

        meta = normalize_not_provided(meta)
        validate_metadata_json(meta)
        meta["target_language"] = target_language
        return MetadataResult(metadata=meta, strategy_used="chunked", fallback_reason=reason)
