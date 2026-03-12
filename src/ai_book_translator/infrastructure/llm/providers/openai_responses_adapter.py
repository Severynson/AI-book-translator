from __future__ import annotations

import os
import random
import time
from typing import Any, Dict, List, Optional

import requests

from ..types import LLMCapabilities, LLMRequest, LLMResponse
from ..exceptions import (
    LLMError,
    TransientLLMError,
    UploadNotSupportedError,
    UploadFailedError,
)
from ....domain.llm_config import OpenAIConfig


class OpenAIResponsesAdapter:
    """OpenAI Responses API adapter implementing the LLMClient protocol."""

    def __init__(self, config: OpenAIConfig):
        if not config.api_key:
            raise ValueError(
                "Missing OpenAI API key. Pass api_key in config or set OPENAI_API_KEY."
            )
        self._config = config
        self.base_url = config.base_url.rstrip("/")
        self.model = config.model
        self.api_key = config.api_key
        self.timeout_sec = config.timeout_sec

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_file_upload=True,
            supports_json_schema=True,
        )

    def test_connection(self) -> None:
        self.generate_text(
            LLMRequest(
                system_prompt="You are a helpful assistant.",
                user_prompt="Reply with exactly: OK",
                max_tokens=512,
            )
        )

    def generate_text(self, request: LLMRequest) -> LLMResponse:
        if request.file_path:
            return self._generate_with_file(request)
        return self._generate_text_only(request)

    # ---- internal ----

    def _generate_text_only(self, request: LLMRequest) -> LLMResponse:
        url = f"{self.base_url}/v1/responses"
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        self._apply_options(payload, request)
        resp = self._post_json(url, payload)
        text = self._extract_output_text(resp)
        if not text:
            raise LLMError(f"Empty output_text from Responses API. Raw: {resp}")
        return LLMResponse(text=text, raw=resp)

    def _generate_with_file(self, request: LLMRequest) -> LLMResponse:
        file_id = self._upload_file(request.file_path)
        url = f"{self.base_url}/v1/responses"
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": request.system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_file", "file_id": file_id},
                        {"type": "input_text", "text": request.user_prompt},
                    ],
                },
            ],
        }
        self._apply_options(payload, request)

        try:
            resp = self._post_json(url, payload)
        except LLMError as e:
            msg = str(e).lower()
            # Schema validation errors are NOT upload errors — let them propagate
            if "json_schema" in msg or "response_format" in msg or "schema" in msg:
                raise
            if any(
                s in msg
                for s in ["input_file", "file_id", "unsupported",
                          "cannot", "not allowed"]
            ):
                raise UploadNotSupportedError(
                    f"File input rejected by model/API: {e}"
                ) from e
            raise

        text = self._extract_output_text(resp)
        if not text:
            raise UploadFailedError(
                f"Empty output_text after file input. Raw: {resp}"
            )
        return LLMResponse(text=text, raw=resp)

    def _apply_options(self, payload: Dict[str, Any], request: LLMRequest) -> None:
        if request.max_tokens is not None:
            payload["max_output_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.json_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "strict": True,
                    "name": "structured_output",
                    "schema": request.json_schema,
                }
            }

    # ---- HTTP helpers ----

    def _headers_json(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _headers_multipart(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        max_attempts = 4
        base_sleep = 1.0
        last_err: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                r = requests.post(
                    url,
                    headers=self._headers_json(),
                    json=payload,
                    timeout=self.timeout_sec,
                )
            except requests.Timeout as e:
                last_err = e
                time.sleep(base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.25))
                continue
            except requests.RequestException as e:
                last_err = e
                time.sleep(base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.25))
                continue

            if r.status_code in (429, 500, 502, 503, 504):
                last_err = TransientLLMError(
                    f"Transient error {r.status_code}: {r.text[:500]}"
                )
                time.sleep(base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.25))
                continue

            if r.status_code >= 400:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:1200]}")

            return r.json()

        detail = f" Last error: {last_err}" if last_err else ""
        raise TransientLLMError(
            f"Failed after {max_attempts} attempts calling {url}.{detail}"
        ) from last_err

    def _extract_output_text(self, resp: Dict[str, Any]) -> str:
        out_items = resp.get("output", []) or []
        parts: List[str] = []
        for item in out_items:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for c in item.get("content", []) or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") in ("output_text", "text"):
                    txt = c.get("text")
                    if isinstance(txt, str) and txt:
                        parts.append(txt)
        return "".join(parts).strip()

    def _upload_file(self, file_path: str) -> str:
        files_url = f"{self.base_url}/v1/files"
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                data = {"purpose": "user_data"}
                r = requests.post(
                    files_url,
                    headers=self._headers_multipart(),
                    files=files,
                    data=data,
                    timeout=self.timeout_sec,
                )
        except FileNotFoundError as e:
            raise UploadFailedError(f"File not found: {file_path}") from e
        except requests.Timeout as e:
            raise TransientLLMError(f"Timeout uploading to {files_url}") from e
        except requests.RequestException as e:
            raise TransientLLMError(f"Network error uploading to {files_url}: {e}") from e

        if r.status_code in (429, 500, 502, 503, 504):
            raise TransientLLMError(f"Transient upload error {r.status_code}: {r.text[:500]}")
        if r.status_code in (404, 405):
            raise UploadNotSupportedError(f"Files endpoint not available: HTTP {r.status_code}")
        if r.status_code >= 400:
            raise UploadFailedError(f"Upload failed HTTP {r.status_code}: {r.text[:1200]}")

        file_data = r.json()
        file_id = file_data.get("id")
        if not file_id:
            raise UploadFailedError(f"Upload succeeded but no file id returned: {file_data}")
        return file_id
