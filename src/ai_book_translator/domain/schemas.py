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

    # Type checks (optional but recommended)
    if not isinstance(obj.get("author(s)"), str):
        raise SchemaValidationError('"author(s)" must be a string')
    if not isinstance(obj.get("title"), str):
        raise SchemaValidationError('"title" must be a string')
    if not isinstance(obj.get("language"), str):
        raise SchemaValidationError('"language" must be a string')
    if not isinstance(obj.get("summary"), str):
        raise SchemaValidationError('"summary" must be a string')
    if not isinstance(obj.get("chapters"), dict):
        raise SchemaValidationError('"chapters" must be an object/dict')

    # Ensure chapters values are correct structure
    for k, v in obj["chapters"].items():
        if not isinstance(k, str):
            raise SchemaValidationError('"chapters" keys must be strings')
        
        # New structure check
        if not isinstance(v, dict):
             raise SchemaValidationError(f'"chapters" value for "{k}" must be an object with "general" and "detailed"')
        
        if "general" not in v or "detailed" not in v:
             raise SchemaValidationError(f'"chapters" value for "{k}" missing "general" or "detailed"')
        
        if not isinstance(v.get("general"), str) or not isinstance(v.get("detailed"), str):
             raise SchemaValidationError(f'"chapters" value for "{k}" must have string values for "general" and "detailed"')


def normalize_not_provided(obj: Dict[str, Any]) -> Dict[str, Any]:
    # Normalize missing / empty strings to "not provided"
    for k in REQUIRED_KEYS:
        v = obj.get(k)
        if v is None:
            obj[k] = "not provided"
        elif isinstance(v, str) and not v.strip():
            obj[k] = "not provided"

    # Normalize author(s): list -> comma-separated string
    a = obj.get("author(s)")
    if isinstance(a, list):
        joined = ", ".join(str(x).strip() for x in a if str(x).strip())
        obj["author(s)"] = joined or "not provided"
    elif a is None:
        obj["author(s)"] = "not provided"

    # Normalize chapters: if model returned "not provided" string, convert to {}
    ch = obj.get("chapters")
    if isinstance(ch, str):
        if ch.strip().lower() == "not provided":
            obj["chapters"] = {}
    elif ch is None:
        obj["chapters"] = {}

    return obj
