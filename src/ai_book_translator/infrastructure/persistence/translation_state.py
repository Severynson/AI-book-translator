from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from .paths import state_dir


def _default_state_dir() -> Path:
    d = state_dir() / "translation_state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def compute_document_hash(full_text: str) -> str:
    data = (full_text or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(data).hexdigest()


def _safe_filename(s: str, max_len: int = 80) -> str:
    s = (s or "").strip()
    s = re.sub(r"[\\/:*?\"<>|]+", "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return "document"
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def make_state_path(*, title: Optional[str], doc_hash: str) -> Path:
    # Prefer human-friendly title if present; always include hash prefix for uniqueness.
    base = _safe_filename(title or "")
    if not base or base == "not provided":
        base = doc_hash[:16]
    name = f"{base}__{doc_hash[:16]}.json"
    return _default_state_dir() / name


def iter_state_files() -> list[Path]:
    d = _default_state_dir()
    return sorted(d.glob("*.json"))


def load_state(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, obj: Dict[str, Any]) -> None:
    # Atomic-ish write: write temp then replace
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def delete_state(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)  # py3.8+: missing_ok
    except Exception:
        # Best-effort cleanup
        pass


def find_state_by_hash(doc_hash: str) -> Optional[Tuple[Path, Dict[str, Any]]]:
    for p in iter_state_files():
        try:
            obj = load_state(p)
        except Exception:
            continue
        if obj.get("document_hash") == doc_hash:
            return p, obj
    return None
