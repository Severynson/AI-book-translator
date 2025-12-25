from __future__ import annotations
from pathlib import Path
import json
from typing import Any, Dict, Optional

from .paths import state_path_for_hash


class StateStore:
    def load(self, doc_hash: str) -> Optional[Dict[str, Any]]:
        p = state_path_for_hash(doc_hash)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def save(self, doc_hash: str, state: Dict[str, Any]) -> None:
        p = state_path_for_hash(doc_hash)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete(self, doc_hash: str) -> None:
        p = state_path_for_hash(doc_hash)
        if p.exists():
            p.unlink()
