#!/usr/bin/env python3
"""Debug script: run metadata generation without GUI.

Usage:
    python debug_metadata.py --provider openai --model gpt-4o-mini --file path/to/book.pdf
    python debug_metadata.py --provider openai --model gpt-4o-mini --text "Paste some text here"
    python debug_metadata.py --provider ollama --model llama3.1 --file path/to/book.txt

Environment:
    OPENAI_API_KEY  — required when --provider=openai and --api-key not given
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.llm_config import OpenAIConfig, OllamaConfig
from ai_book_translator.domain.models import DocumentInput
from ai_book_translator.domain.schemas import normalize_not_provided, validate_metadata_json
from ai_book_translator.infrastructure.llm.provider_factory import create_client
from ai_book_translator.infrastructure.llm.types import LLMRequest
from ai_book_translator.services.connection_service import ConnectionService
from ai_book_translator.services.document_service import ensure_raw_text
from ai_book_translator.services.metadata_service import MetadataService, METADATA_SCHEMA
from ai_book_translator.services.llm_json_client import LLMJsonClient
from ai_book_translator.services.prompts import (
    METADATA_SYSTEM_PROMPT,
    METADATA_USER_PROMPT_UPLOAD,
)


def _sep(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug metadata generation (no GUI)")
    parser.add_argument("--provider", choices=["openai", "ollama"], default="openai")
    parser.add_argument("--api-key", default=None, help="OpenAI API key (or set OPENAI_API_KEY)")
    parser.add_argument("--base-url", default=None, help="Ollama base URL")
    parser.add_argument("--model", default=None, help="Model name")
    parser.add_argument("--file", default=None, help="Path to PDF or TXT file")
    parser.add_argument("--text", default=None, help="Direct text input (instead of file)")
    parser.add_argument("--target-language", default="English", help="Target language")
    parser.add_argument("--chunk-chars", type=int, default=8000, help="Metadata chunk size")
    args = parser.parse_args()

    # --- Build config ---
    if args.provider == "openai":
        api_key = args.api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            print("ERROR: No API key. Pass --api-key or set OPENAI_API_KEY.")
            sys.exit(1)
        model = args.model or "gpt-4o-mini"
        config = OpenAIConfig(api_key=api_key, model=model)
    else:
        base_url = args.base_url or "http://localhost:11434"
        model = args.model or "llama3.1"
        config = OllamaConfig(base_url=base_url, model=model)

    client = create_client(config)

    # --- Connection test ---
    _sep("CONNECTION TEST")
    try:
        ConnectionService(client).test()
        print("OK — connection successful")
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

    # --- Prepare document ---
    _sep("DOCUMENT PREPARATION")
    if args.file:
        doc = DocumentInput(file_path=args.file)
        doc = ensure_raw_text(doc)
        print(f"File: {args.file}")
    elif args.text:
        doc = DocumentInput(raw_text=args.text)
        print(f"Direct text input ({len(args.text)} chars)")
    else:
        print("ERROR: provide --file or --text")
        sys.exit(1)

    if doc.raw_text:
        print(f"Raw text length: {len(doc.raw_text)} chars")
        print(f"First 500 chars:\n{doc.raw_text[:500]}")
    else:
        print("WARNING: raw_text is None (upload-only path will be used)")

    # --- Show what prompts will be sent ---
    _sep("SYSTEM PROMPT (metadata)")
    print(METADATA_SYSTEM_PROMPT)

    # --- Step A: Raw LLM call (no parsing, no schema) ---
    _sep("STEP A — RAW LLM CALL (prompt-only, no schema enforcement)")
    print("Sending raw request to see exactly what the model returns...\n")

    caps = client.capabilities()
    print(f"Client capabilities: supports_file_upload={caps.supports_file_upload}, "
          f"supports_json_schema={caps.supports_json_schema}")

    if doc.raw_text:
        user_prompt = (
            "Return the metadata JSON for the following document text.\n\n"
            f"{doc.raw_text[:15000]}"
        )
    else:
        user_prompt = METADATA_USER_PROMPT_UPLOAD

    try:
        request = LLMRequest(
            system_prompt=METADATA_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            file_path=doc.file_path if caps.supports_file_upload else None,
            max_tokens=2000,
        )
        resp = client.generate_text(request)
        print("--- RAW RESPONSE TEXT ---")
        print(resp.text)
        print("--- END RAW RESPONSE ---")
        print(f"\nResponse length: {len(resp.text)} chars")
    except Exception as e:
        print(f"RAW CALL FAILED: {e}")
        traceback.print_exc()

    # --- Step B: Schema-enforced LLM call ---
    if caps.supports_json_schema:
        _sep("STEP B — SCHEMA-ENFORCED LLM CALL")
        try:
            request = LLMRequest(
                system_prompt=METADATA_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                file_path=doc.file_path if caps.supports_file_upload else None,
                json_schema=METADATA_SCHEMA,
                max_tokens=2000,
            )
            resp = client.generate_text(request)
            print("--- SCHEMA-ENFORCED RESPONSE TEXT ---")
            print(resp.text)
            print("--- END SCHEMA-ENFORCED RESPONSE ---")
        except Exception as e:
            print(f"SCHEMA-ENFORCED CALL FAILED: {e}")
            traceback.print_exc()
    else:
        print("\n[SKIP] Schema enforcement not supported by this provider.")

    # --- Step C: Full MetadataService pipeline ---
    _sep("STEP C — FULL MetadataService.generate_metadata() PIPELINE")
    settings = Settings(local_metadata_chunk_chars=args.chunk_chars)

    try:
        service = MetadataService(client, settings)
        result = service.generate_metadata(doc, args.target_language)

        print(f"Strategy used: {result.strategy_used}")
        if result.fallback_reason:
            print(f"Fallback reason: {result.fallback_reason}")

        print("\n--- FINAL METADATA JSON ---")
        print(json.dumps(result.metadata, indent=2, ensure_ascii=False))
        print("--- END METADATA JSON ---")

    except Exception as e:
        print(f"MetadataService FAILED: {e}")
        traceback.print_exc()

        # Try to show what normalize + validate would do with the raw response
        _sep("STEP D — DEBUG: manual normalize + validate on raw response")
        try:
            # Re-do raw call and parse
            from ai_book_translator.infrastructure.llm.json_parser import (
                parse_json_strict,
                extract_json_object_loose,
            )
            request = LLMRequest(
                system_prompt=METADATA_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=2000,
            )
            resp = client.generate_text(request)
            print(f"Raw response:\n{resp.text}\n")

            # Try parsing
            obj = None
            try:
                obj = parse_json_strict(resp.text)
                print("parse_json_strict: OK")
            except Exception as pe:
                print(f"parse_json_strict failed: {pe}")
                extracted = extract_json_object_loose(resp.text)
                if extracted:
                    print(f"extract_json_object_loose found:\n{extracted}\n")
                    try:
                        obj = parse_json_strict(extracted)
                        print("parse_json_strict on extracted: OK")
                    except Exception as pe2:
                        print(f"parse_json_strict on extracted failed: {pe2}")

            if obj:
                print(f"\nParsed keys: {list(obj.keys())}")
                print(f"Parsed JSON:\n{json.dumps(obj, indent=2, ensure_ascii=False)}\n")

                print("Running normalize_not_provided()...")
                obj = normalize_not_provided(obj)
                print(f"After normalize keys: {list(obj.keys())}")
                print(f"After normalize:\n{json.dumps(obj, indent=2, ensure_ascii=False)}\n")

                print("Running validate_metadata_json()...")
                try:
                    validate_metadata_json(obj)
                    print("VALIDATION PASSED")
                except Exception as ve:
                    print(f"VALIDATION FAILED: {ve}")

        except Exception as de:
            print(f"Debug step failed: {de}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
