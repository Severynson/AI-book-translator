from __future__ import annotations
from typing import Any, Dict

from ..infrastructure.llm.base import LLMProvider
from ..infrastructure.llm.json_parser import parse_json_strict, extract_json_object_loose
from ..infrastructure.llm.exceptions import InvalidJSONError

def chat_json_strict_with_repair(
    provider: LLMProvider,
    system_prompt: str,
    user_prompt: str,
    repair_retries: int = 2,
    **kwargs: Any
) -> Dict[str, Any]:
    raw = provider.chat_text(system_prompt=system_prompt, user_prompt=user_prompt, **kwargs)

    try:
        return parse_json_strict(raw)
    except InvalidJSONError:
        extracted = extract_json_object_loose(raw)
        if extracted:
            try:
                return parse_json_strict(extracted)
            except InvalidJSONError:
                pass

    bad = raw
    last_err: Exception | None = None
    for _ in range(repair_retries):
        fix_system = "Return STRICT JSON only. No extra text."
        fix_user = (
            "Rewrite the following into valid JSON matching the required schema. "
            "Return only JSON.\n\n"
            f"{bad}"
        )
        bad = provider.chat_text(system_prompt=fix_system, user_prompt=fix_user, **kwargs)
        try:
            return parse_json_strict(bad)
        except InvalidJSONError as e:
            last_err = e
            continue

    raise InvalidJSONError(f"Could not parse/repair JSON after retries: {last_err}")
