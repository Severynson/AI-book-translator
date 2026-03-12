"""Persists last N unique values for UI input fields.

Storage: state/field_history.json (gitignored via state/ rule).
Each field key maps to a list of entries, newest first:
  { "value": "...", "used_at": <unix_timestamp> }
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from ai_book_translator.infrastructure.persistence.paths import state_dir

MAX_ENTRIES_PER_FIELD = 5
_FILENAME = "field_history.json"


def _history_path() -> Path:
    return state_dir() / _FILENAME


def load_all() -> Dict[str, List[Dict[str, Any]]]:
    p = _history_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_all(data: Dict[str, List[Dict[str, Any]]]) -> None:
    p = _history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def get_field_values(field_key: str) -> List[str]:
    """Return up to MAX_ENTRIES_PER_FIELD most recent unique values for a field."""
    data = load_all()
    entries = data.get(field_key, [])
    return [e["value"] for e in entries if isinstance(e, dict) and "value" in e]


def push_field_value(field_key: str, value: str) -> None:
    """Record a value for a field. Deduplicates and keeps newest first."""
    value = value.strip()
    if not value:
        return

    data = load_all()
    entries = data.get(field_key, [])

    # Remove existing entry with same value (will re-add at front)
    entries = [e for e in entries if e.get("value") != value]

    # Prepend new entry
    entries.insert(0, {"value": value, "used_at": int(time.time())})

    # Trim to max
    entries = entries[:MAX_ENTRIES_PER_FIELD]

    data[field_key] = entries
    save_all(data)


def push_many(field_values: Dict[str, str]) -> None:
    """Record multiple field values in a single write."""
    data = load_all()

    for field_key, value in field_values.items():
        value = value.strip()
        if not value:
            continue

        entries = data.get(field_key, [])
        entries = [e for e in entries if e.get("value") != value]
        entries.insert(0, {"value": value, "used_at": int(time.time())})
        entries = entries[:MAX_ENTRIES_PER_FIELD]
        data[field_key] = entries

    save_all(data)
