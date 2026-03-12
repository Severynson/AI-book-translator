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
    lang = obj.get("language")
    if not isinstance(lang, list):
        raise SchemaValidationError('"language" must be an array of strings')
    for item in lang:
        if not isinstance(item, str):
            raise SchemaValidationError('"language" array must contain only strings')
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
    # Fix common LLM mistake: "author" or "authors" instead of "author(s)"
    for wrong_key in ("author", "authors"):
        if wrong_key in obj and "author(s)" not in obj:
            obj["author(s)"] = obj.pop(wrong_key)
        elif wrong_key in obj:
            obj.pop(wrong_key)

    # Fix common LLM mistake: "languages" instead of "language"
    if "languages" in obj and "language" not in obj:
        obj["language"] = obj.pop("languages")
    elif "languages" in obj:
        obj.pop("languages")

    # Strip any unexpected keys (LLMs sometimes add "error", "contributors",
    # "notes", etc.).  Keep only REQUIRED_KEYS + "target_language".
    allowed = set(REQUIRED_KEYS) | {"target_language"}
    for k in list(obj.keys()):
        if k not in allowed:
            obj.pop(k)

    # Normalize missing / empty strings to "not provided"
    # (skip "language" — handled separately as an array)
    for k in REQUIRED_KEYS:
        if k == "language":
            continue
        v = obj.get(k)
        if v is None:
            obj[k] = "not provided"
        elif isinstance(v, str) and not v.strip():
            obj[k] = "not provided"

    # Normalize language: ensure it is a list of strings
    lang = obj.get("language")
    if lang is None or (isinstance(lang, str) and not lang.strip()):
        obj["language"] = ["not provided"]
    elif isinstance(lang, str):
        # Legacy string format → single-element list
        obj["language"] = [lang]
    elif isinstance(lang, list):
        if not lang:
            obj["language"] = ["not provided"]
        else:
            # Ensure all items are strings
            obj["language"] = [str(item) for item in lang if str(item).strip()]
            if not obj["language"]:
                obj["language"] = ["not provided"]

    # Normalize author(s): list -> comma-separated string
    a = obj.get("author(s)")
    if isinstance(a, list):
        joined = ", ".join(str(x).strip() for x in a if str(x).strip())
        obj["author(s)"] = joined or "not provided"
    elif a is None:
        obj["author(s)"] = "not provided"

    # Normalize chapters: must be a dict with {name: {general, detailed}} structure
    ch = obj.get("chapters")
    if isinstance(ch, dict):
        # Strip chapter entries that don't have the required structure;
        # coerce string values to {general: value, detailed: value}
        cleaned: Dict[str, Any] = {}
        for ck, cv in ch.items():
            if not isinstance(ck, str):
                continue
            if isinstance(cv, dict) and "general" in cv and "detailed" in cv:
                cleaned[ck] = cv
            elif isinstance(cv, str):
                # LLM returned a flat string instead of {general, detailed}
                cleaned[ck] = {"general": cv, "detailed": cv}
        obj["chapters"] = cleaned
    elif isinstance(ch, list):
        # LLM returned an array of chapter objects — try to convert
        converted: Dict[str, Any] = {}
        for item in ch:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("title") or item.get("chapter") or "")
                if name:
                    gen = str(item.get("general", item.get("summary", "")))
                    det = str(item.get("detailed", item.get("description", gen)))
                    converted[name] = {"general": gen, "detailed": det}
        obj["chapters"] = converted
    elif isinstance(ch, str):
        obj["chapters"] = {}
    else:
        obj["chapters"] = {}

    return obj
