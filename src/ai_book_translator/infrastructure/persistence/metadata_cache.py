from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from .paths import state_dir

def _default_state_dir() -> Path:
    d = state_dir() / "metadata_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slugify(name: str, max_len: int = 80) -> str:
    name = (name or "").strip()
    if not name:
        return "untitled"
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[^a-zA-Z0-9 _\-\(\)\[\]\.]", "", name)
    name = name.strip().replace(" ", "_")
    return name[:max_len] or "untitled"


@dataclass(frozen=True)
class MetadataCacheRecord:
    document_hash: str
    target_language: str
    metadata: Dict[str, Any]
    created_at: float
    title_hint: str


def _cache_path_for(document_hash: str, title_hint: str, state_dir: Optional[Path] = None) -> Path:
    d = state_dir or _default_state_dir()
    slug = _slugify(title_hint) if title_hint else "metadata"
    # Include hash so multiple “Untitled” docs don’t collide.
    return d / f"{slug}.{document_hash}.metadata_cache.json"


def save_metadata_cache(
    *,
    document_hash: str,
    metadata: Dict[str, Any],
    target_language: str,
    title_hint: str = "",
    state_dir: Optional[Path] = None,
) -> Path:
    rec = MetadataCacheRecord(
        document_hash=document_hash,
        target_language=target_language,
        metadata=dict(metadata or {}),
        created_at=time.time(),
        title_hint=title_hint or "",
    )
    p = _cache_path_for(document_hash, title_hint=title_hint, state_dir=state_dir)
    tmp = p.with_suffix(p.suffix + ".tmp")

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            {
                "document_hash": rec.document_hash,
                "target_language": rec.target_language,
                "metadata": rec.metadata,
                "created_at": rec.created_at,
                "title_hint": rec.title_hint,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    tmp.replace(p)
    return p


def find_metadata_cache_by_hash(
    document_hash: str,
    *,
    state_dir: Optional[Path] = None,
) -> Optional[Path]:
    d = state_dir or _default_state_dir()
    if not d.exists():
        return None

    # file name includes ".{hash}.metadata_cache.json"
    suffix = f".{document_hash}.metadata_cache.json"
    for p in d.glob(f"*{suffix}"):
        if p.is_file():
            return p
    return None


def load_metadata_cache(path: str | Path) -> MetadataCacheRecord:
    p = Path(path)
    with open(p, "r", encoding="utf-8") as f:
        obj = json.load(f)

    return MetadataCacheRecord(
        document_hash=str(obj.get("document_hash") or ""),
        target_language=str(obj.get("target_language") or ""),
        metadata=dict(obj.get("metadata") or {}),
        created_at=float(obj.get("created_at") or 0.0),
        title_hint=str(obj.get("title_hint") or ""),
    )


def delete_metadata_cache_for_hash(document_hash: str, *, state_dir: Optional[Path] = None) -> None:
    d = state_dir or _default_state_dir()
    suffix = f".{document_hash}.metadata_cache.json"
    for p in d.glob(f"*{suffix}"):
        try:
            p.unlink()
        except Exception:
            pass