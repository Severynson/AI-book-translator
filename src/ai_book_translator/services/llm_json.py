"""Backward-compatible JSON generation helper.

New code should use LLMJsonClient from services.llm_json_client instead.
This module is kept so existing tests continue to work until migrated.
"""
from __future__ import annotations

from typing import Any, Dict

from ..infrastructure.llm.client import LLMClient
from ..infrastructure.llm.types import LLMRequest
from ..infrastructure.llm.json_parser import parse_json_strict, extract_json_object_loose
from ..infrastructure.llm.exceptions import InvalidJSONError


def chat_json_strict_with_repair(
    provider: LLMClient,
    system_prompt: str,
    user_prompt: str,
    repair_retries: int = 2,
    **kwargs: Any,
) -> Dict[str, Any]:
    request = LLMRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    resp = provider.generate_text(request)
    raw = resp.text

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
        fix_request = LLMRequest(
            system_prompt="Return STRICT JSON only. No extra text.",
            user_prompt=(
                "Rewrite the following into valid JSON matching the required schema. "
                f"Return only JSON.\n\n{bad}"
            ),
        )
        resp = provider.generate_text(fix_request)
        bad = resp.text
        try:
            return parse_json_strict(bad)
        except InvalidJSONError as e:
            last_err = e
            continue

    raise InvalidJSONError(f"Could not parse/repair JSON after retries: {last_err}")
