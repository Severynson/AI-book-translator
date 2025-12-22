from __future__ import annotations
import json
from typing import Any, Dict, Optional
from .exceptions import InvalidJSONError

def parse_json_strict(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        obj = json.loads(text)
    except Exception as e:
        raise InvalidJSONError(f"Failed to parse JSON: {e}") from e
    if not isinstance(obj, dict):
        raise InvalidJSONError("Top-level JSON must be an object/dict.")
    return obj

def extract_json_object_loose(text: str) -> Optional[str]:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end+1]
