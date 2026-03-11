from __future__ import annotations

from typing import Any, Dict, Optional

from ai_book_translator.infrastructure.llm.client import LLMClient
from ai_book_translator.infrastructure.llm.types import LLMRequest
from ai_book_translator.infrastructure.llm.json_parser import (
    parse_json_strict,
    extract_json_object_loose,
)
from ai_book_translator.infrastructure.llm.exceptions import InvalidJSONError


class LLMJsonClient:
    """Centralized JSON generation with schema attempt, parse, and repair loop.

    Replaces duplicated JSON handling across metadata and translation flows.
    """

    def __init__(self, client: LLMClient, repair_retries: int = 2):
        self._client = client
        self._repair_retries = repair_retries

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        file_path: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate and parse a JSON response from the LLM.

        Strategy:
        1. If json_schema provided and client supports it, try schema-enforced output.
        2. Fall back to prompt-enforced output.
        3. Try strict parse, then loose extraction.
        4. Repair loop with bounded retries.
        """
        caps = self._client.capabilities()
        effective_file = file_path if caps.supports_file_upload else None

        # 1. Schema-enforced attempt (if supported)
        if json_schema and caps.supports_json_schema:
            try:
                request = LLMRequest(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    file_path=effective_file,
                    json_schema=json_schema,
                    max_tokens=max_tokens,
                )
                resp = self._client.generate_text(request)
                return parse_json_strict(resp.text)
            except InvalidJSONError:
                pass  # fall through to prompt-only
            except Exception:
                pass  # schema mode failed entirely, fall through

        # 2. Prompt-enforced attempt (no schema)
        request = LLMRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            file_path=effective_file,
            max_tokens=max_tokens,
        )
        resp = self._client.generate_text(request)

        # Try parsing
        result = self._try_parse(resp.text)
        if result is not None:
            return result

        # 3. Repair loop
        return self._repair_loop(resp.text)

    def generate_json_text_only(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate JSON without file upload (convenience for translation chunks)."""
        return self.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
        )

    def _try_parse(self, raw: str) -> Optional[Dict[str, Any]]:
        try:
            return parse_json_strict(raw)
        except InvalidJSONError:
            pass

        extracted = extract_json_object_loose(raw)
        if extracted:
            try:
                return parse_json_strict(extracted)
            except InvalidJSONError:
                pass

        return None

    def _repair_loop(self, bad: str) -> Dict[str, Any]:
        last_err: Exception | None = None
        for _ in range(self._repair_retries):
            repair_request = LLMRequest(
                system_prompt="Return STRICT JSON only. No extra text.",
                user_prompt=(
                    "Rewrite the following into valid JSON matching the required schema. "
                    f"Return only JSON.\n\n{bad}"
                ),
            )
            resp = self._client.generate_text(repair_request)
            try:
                return parse_json_strict(resp.text)
            except InvalidJSONError as e:
                last_err = e
                bad = resp.text
                continue

        raise InvalidJSONError(
            f"Could not parse/repair JSON after retries: {last_err}"
        )
