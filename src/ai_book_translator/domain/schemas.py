from __future__ import annotations
from typing import Any, Dict
from ..infrastructure.llm.exceptions import SchemaValidationError

REQUIRED_KEYS = ["author(s)", "title", "language", "summary", "chapters"]

def validate_metadata_json(obj: Dict[str, Any]) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in obj]
    if missing:
        raise SchemaValidationError(f"Metadata JSON missing keys: {missing}")
    extra = [k for k in obj.keys() if k not in REQUIRED_KEYS and k != "target_language"]
    if extra:
        raise SchemaValidationError(f"Metadata JSON has extra keys: {extra}")

def normalize_not_provided(obj: Dict[str, Any]) -> Dict[str, Any]:
    for k in REQUIRED_KEYS:
        v = obj.get(k)
        if v is None:
            obj[k] = "not provided"
        elif isinstance(v, str) and not v.strip():
            obj[k] = "not provided"
    return obj
