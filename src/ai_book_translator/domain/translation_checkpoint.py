from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


CHECKPOINT_SCHEMA_VERSION = 1


@dataclass
class TranslationCheckpoint:
    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    document_hash: str = ""
    document_path: str = ""          # absolute path (empty for pasted text)
    target_language: str = ""
    llm_config: Dict[str, Any] = field(default_factory=dict)
    settings_snapshot: Dict[str, Any] = field(default_factory=dict)
    next_chunk_index: int = 0        # first chunk NOT yet committed
    chunks_total: int = 0
    current_chapter: str = ""
    previous_tail: str = ""
    output_txt_path: str = ""        # absolute path to output file
    metadata_path: str = ""          # absolute path to cached metadata JSON
    translation_chunk_chars: int = 30000
    updated_at_unix: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["updated_at_unix"] = int(time.time())
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TranslationCheckpoint":
        return cls(
            schema_version=int(d.get("schema_version", 1)),
            document_hash=str(d.get("document_hash", "")),
            document_path=str(d.get("document_path", "")),
            target_language=str(d.get("target_language", "")),
            llm_config=dict(d.get("llm_config") or {}),
            settings_snapshot=dict(d.get("settings_snapshot") or {}),
            next_chunk_index=int(d.get("next_chunk_index") or d.get("current_chunk_index") or 0),
            chunks_total=int(d.get("chunks_total", 0)),
            current_chapter=str(d.get("current_chapter", "")),
            previous_tail=str(d.get("previous_tail") or d.get("last_translation_tail") or ""),
            output_txt_path=str(d.get("output_txt_path", "")),
            metadata_path=str(d.get("metadata_path", "")),
            translation_chunk_chars=int(d.get("translation_chunk_chars", 30000)),
            updated_at_unix=int(d.get("updated_at_unix", 0)),
        )
