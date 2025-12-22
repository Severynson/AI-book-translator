from __future__ import annotations
import os
from typing import Any, Dict, Optional, List, Tuple
import requests
import time
import random
from .base import LLMProvider
from .exceptions import (
    LLMError,
    UploadNotSupportedError,
    UploadFailedError,
    TransientLLMError,
)


class OpenAIResponsesProvider(LLMProvider):
    """
    OpenAI provider using the Responses API.

    - text: POST https://api.openai.com/v1/responses
    - file upload: POST https://api.openai.com/v1/files (purpose=user_data recommended for model inputs)

    Default model: gpt-5-nano
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-5-nano",
        base_url: str = "https://api.openai.com",
        timeout_sec: int = 400,
    ):
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing OpenAI API key. Pass api_key=... or set OPENAI_API_KEY."
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_sec = timeout_sec

    def _headers_json(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _headers_multipart(self) -> Dict[str, str]:
        # IMPORTANT: no Content-Type; requests will set multipart boundary.
        return {"Authorization": f"Bearer {self.api_key}"}

    def test_connection(self) -> None:
        _ = self.chat_text(
            system_prompt="You are a helpful assistant.",
            user_prompt="Reply with exactly: OK",
            max_output_tokens=512,
        )

    # ---------- Core helpers ----------

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Try a few times on timeouts / transient codes
        max_attempts = 4
        base_sleep = 1.0

        last_err: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                r = requests.post(
                    url,
                    headers=self._headers_json(),
                    json=payload,
                    timeout=self.timeout_sec,  # consider 180–300 for big docs
                )
            except requests.Timeout as e:
                last_err = e
                # backoff
                sleep_s = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                time.sleep(sleep_s)
                continue
            except requests.RequestException as e:
                last_err = e
                sleep_s = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                time.sleep(sleep_s)
                continue

            # transient http statuses
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = TransientLLMError(
                    f"Transient error {r.status_code}: {r.text[:500]}"
                )
                sleep_s = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                time.sleep(sleep_s)
                continue

            if r.status_code >= 400:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:1200]}")

            return r.json()

        raise TransientLLMError(f"Timeout/Network failure calling {url}") from last_err

    def _extract_output_text(self, resp: Dict[str, Any]) -> str:
        """
        Robustly extract assistant text from Responses API response.
        The API returns an `output` array of items; we gather text chunks.
        """
        out_items = resp.get("output", []) or []
        parts: List[str] = []

        for item in out_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content", []) or []
            # content elements typically look like:
            # { "type": "output_text", "text": "..." }
            for c in content:
                if not isinstance(c, dict):
                    continue
                ctype = c.get("type")
                if ctype in ("output_text", "text"):
                    txt = c.get("text")
                    if isinstance(txt, str) and txt:
                        parts.append(txt)

        return "".join(parts).strip()

    # ---------- Public API ----------

    def chat_text(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        url = f"{self.base_url}/v1/responses"

        # Responses API accepts either a string input or an array of message-like items.
        # We'll use the array form so you can pass system + user cleanly.
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        # Map common kwargs (keep your call sites similar)
        # Responses API uses max_output_tokens (not max_tokens).
        if "max_tokens" in kwargs and "max_output_tokens" not in kwargs:
            kwargs["max_output_tokens"] = kwargs.pop("max_tokens")

        text = kwargs.pop("text", None)
        if text is not None:
            payload["text"] = text

        payload.update(kwargs)

        resp = self._post_json(url, payload)
        text = self._extract_output_text(resp)
        if not text:
            raise LLMError(
                f"Empty output_text from Responses API. Raw response: {resp}"
            )
        return text

    def chat_text_with_document(
        self,
        system_prompt: str,
        user_prompt: str,
        file_path: str,
        **kwargs: Any,
    ) -> str:
        """
        Upload file via Files API, then reference it in the Responses input using input_file + file_id.

        If OpenAI rejects the file as an input for the chosen model/type,
        we map that to UploadNotSupportedError so your fallback chunking can run.
        """
        file_id = self._upload_file_user_data(file_path)

        url = f"{self.base_url}/v1/responses"

        # Build input: user message contains both the file and the question/instructions.
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_file", "file_id": file_id},
                        {"type": "input_text", "text": user_prompt},
                    ],
                },
            ],
        }

        if "max_tokens" in kwargs and "max_output_tokens" not in kwargs:
            kwargs["max_output_tokens"] = kwargs.pop("max_tokens")

        text = kwargs.pop("text", None)
        if text is not None:
            payload["text"] = text

        payload.update(kwargs)

        try:
            resp = self._post_json(url, payload)
        except LLMError as e:
            # If the model/endpoint refuses file input, treat as "not supported" for upload-first.
            msg = str(e).lower()
            if any(
                s in msg
                for s in [
                    "input_file",
                    "file_id",
                    "unsupported",
                    "invalid",
                    "cannot",
                    "not allowed",
                ]
            ):
                raise UploadNotSupportedError(
                    f"File input rejected by model/API: {e}"
                ) from e
            raise

        text = self._extract_output_text(resp)
        if not text:
            raise UploadFailedError(
                f"Empty output_text after file input. Raw response: {resp}"
            )
        return text

    def _looks_like_unsupported_schema_error(msg: str) -> bool:
        m = msg.lower()
        needles = [
            "json_schema",
            "structured outputs",
            "response format",
            "text.format",
            "unsupported",
        ]
        return any(n in m for n in needles)

    # ---------- File upload ----------

    def _upload_file_user_data(self, file_path: str) -> str:
        files_url = f"{self.base_url}/v1/files"
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                data = {"purpose": "user_data"}  # recommended for model inputs
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
            raise TransientLLMError(
                f"Network error uploading to {files_url}: {e}"
            ) from e

        if r.status_code in (429, 500, 502, 503, 504):
            raise TransientLLMError(
                f"Transient upload error {r.status_code}: {r.text[:500]}"
            )
        if r.status_code >= 400:
            # If endpoint changed / blocked
            if r.status_code in (404, 405):
                raise UploadNotSupportedError(
                    f"Files endpoint not available: HTTP {r.status_code}"
                )
            raise UploadFailedError(
                f"Upload failed HTTP {r.status_code}: {r.text[:1200]}"
            )

        file_data = r.json()
        file_id = file_data.get("id")
        if not file_id:
            raise UploadFailedError(
                f"Upload succeeded but no file id returned: {file_data}"
            )

        return file_id
