from __future__ import annotations

from typing import Any, List

from ..config.settings import Settings
from ..domain.models import DocumentInput, MetadataResult
from ..domain.schemas import validate_metadata_json, normalize_not_provided
from ..infrastructure.llm.client import LLMClient
from ..infrastructure.llm.types import LLMRequest
from ..infrastructure.llm.exceptions import (
    UploadNotSupportedError,
    UploadFailedError,
    TransientLLMError,
    DocumentReadError,
)
from .llm_json_client import LLMJsonClient
from .prompts import (
    METADATA_SYSTEM_PROMPT,
    METADATA_USER_PROMPT_UPLOAD,
    METADATA_REPAIR_PROMPT,
    LOCAL_CHUNK_SUMMARY_SYSTEM_PROMPT,
    build_local_chunk_summary_user_prompt,
    SUMMARY_OF_SUMMARIES_SYSTEM_PROMPT,
    build_summary_of_summaries_user_prompt,
)
from .chunking import chunk_by_chars


METADATA_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["author(s)", "title", "language", "summary", "chapters"],
    "properties": {
        "author(s)": {"type": "string"},
        "title": {"type": "string"},
        "language": {
            "type": "array",
            "items": {"type": "string"},
        },
        "summary": {"type": "string"},
        "chapters": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "general": {"type": "string"},
                    "detailed": {"type": "string"},
                },
                "required": ["general", "detailed"],
                "additionalProperties": False,
            },
        },
    },
}


class MetadataService:
    def __init__(self, client: LLMClient, settings: Settings):
        self._client = client
        self._settings = settings
        self._json_client = LLMJsonClient(client, settings.json_repair_retries)

    def generate_metadata(
        self, doc: DocumentInput, target_language: str, **kwargs: Any
    ) -> MetadataResult:
        caps = self._client.capabilities()

        # Upload-first if file_path provided AND provider supports upload
        if doc.file_path and caps.supports_file_upload:
            try:
                meta = self._json_client.generate_json(
                    system_prompt=METADATA_SYSTEM_PROMPT,
                    user_prompt=METADATA_USER_PROMPT_UPLOAD,
                    file_path=doc.file_path,
                    json_schema=METADATA_SCHEMA,
                    max_tokens=2000,
                )
                meta = normalize_not_provided(meta)
                validate_metadata_json(meta)
                meta["target_language"] = target_language
                return MetadataResult(metadata=meta, strategy_used="upload")

            except (UploadNotSupportedError, UploadFailedError) as e:
                return self._chunked_fallback(
                    doc, target_language, reason=str(e)
                )

            except TransientLLMError:
                for _ in range(self._settings.upload_retries):
                    try:
                        meta = self._json_client.generate_json(
                            system_prompt=METADATA_SYSTEM_PROMPT,
                            user_prompt=METADATA_USER_PROMPT_UPLOAD,
                            file_path=doc.file_path,
                            json_schema=METADATA_SCHEMA,
                            max_tokens=2000,
                        )
                        meta = normalize_not_provided(meta)
                        validate_metadata_json(meta)
                        meta["target_language"] = target_language
                        return MetadataResult(metadata=meta, strategy_used="upload")
                    except TransientLLMError:
                        continue
                    except (UploadNotSupportedError, UploadFailedError) as e:
                        return self._chunked_fallback(
                            doc, target_language, reason=str(e)
                        )
                return self._chunked_fallback(
                    doc, target_language, reason="upload transient failure"
                )

        # No file_path or no upload support → direct chunked fallback
        reason = "no file provided for upload"
        if doc.file_path and not caps.supports_file_upload:
            reason = "provider does not support file upload"
        return self._chunked_fallback(doc, target_language, reason=reason)

    def _chunked_fallback(
        self, doc: DocumentInput, target_language: str, reason: str
    ) -> MetadataResult:
        if doc.raw_text is None:
            raise DocumentReadError(
                "Chunked fallback requires raw_text (extract the document first)."
            )

        chunks = chunk_by_chars(doc.raw_text, self._settings.local_metadata_chunk_chars)

        chunk_summaries: List[str] = []
        for i, ch in enumerate(
            chunks[: self._settings.max_chunk_summaries_for_summary_of_summaries]
        ):
            is_early = (
                i < self._settings.local_metadata_first_chunks_with_title_author_hint
            )
            request = LLMRequest(
                system_prompt=LOCAL_CHUNK_SUMMARY_SYSTEM_PROMPT,
                user_prompt=build_local_chunk_summary_user_prompt(
                    ch, is_early_chunk=is_early
                ),
            )
            resp = self._client.generate_text(request)
            chunk_summaries.append(resp.text.strip())

        meta = self._json_client.generate_json(
            system_prompt=SUMMARY_OF_SUMMARIES_SYSTEM_PROMPT,
            user_prompt=build_summary_of_summaries_user_prompt(chunk_summaries),
        )

        meta = normalize_not_provided(meta)
        validate_metadata_json(meta)
        meta["target_language"] = target_language
        return MetadataResult(
            metadata=meta, strategy_used="chunked", fallback_reason=reason
        )
