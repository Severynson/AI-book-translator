from __future__ import annotations
import argparse, json

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput
from ai_book_translator.infrastructure.llm.openai_compatible_provider import OpenAICompatibleProvider
from ai_book_translator.services.connection_service import ConnectionService
from ai_book_translator.services.metadata_service import MetadataService

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--doc-file", default=None, help="File to attempt upload-first (optional)")
    ap.add_argument("--text-file", default=None, help="Text file to provide raw_text for fallback (recommended)")
    ap.add_argument("--target-language", required=True)
    args = ap.parse_args()

    provider = OpenAICompatibleProvider(args.base_url, args.model, api_key=args.api_key)
    ConnectionService(provider).test()

    raw_text = None
    if args.text_file:
        raw_text = open(args.text_file, "r", encoding="utf-8", errors="ignore").read()

    doc = DocumentInput(file_path=args.doc_file, raw_text=raw_text)
    svc = MetadataService(provider, Settings())
    res = svc.generate_metadata(doc, target_language=args.target_language, temperature=0.2)

    print("strategy_used:", res.strategy_used)
    if res.fallback_reason:
        print("fallback_reason:", res.fallback_reason)
    print(json.dumps(res.metadata, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
