from __future__ import annotations
import argparse, json, os

from ai_book_translator.config.settings import Settings
from ai_book_translator.domain.models import DocumentInput
from ai_book_translator.services.connection_service import ConnectionService
from ai_book_translator.services.metadata_service import MetadataService

from ai_book_translator.infrastructure.llm.openai_provider import OpenAIResponsesProvider
from ai_book_translator.infrastructure.llm.local_provider import LocalOllamaProvider
from ai_book_translator.infrastructure.llm.base import LLMProvider  # parent interface

def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--provider", choices=["openai", "ollama"], required=True)
    ap.add_argument("--model", default="gpt-5-nano")

    # OpenAI
    ap.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY"))
    ap.add_argument("--base-url", default="https://api.openai.com")

    # Ollama
    ap.add_argument("--ollama-url", default="http://localhost:11434")

    ap.add_argument("--doc-file", default=None)
    ap.add_argument("--text-file", default=None)
    ap.add_argument("--target-language", required=True)

    args = ap.parse_args()

    provider: LLMProvider
    if args.provider == "openai":
        if not args.api_key:
            raise SystemExit("Missing --api-key (or set OPENAI_API_KEY).")
        provider = OpenAIResponsesProvider(api_key=args.api_key, model=args.model, base_url=args.base_url)
    else:
        provider = LocalOllamaProvider(base_url=args.ollama_url, model=args.model)

    ConnectionService(provider).test()

    raw_text = None
    if args.text_file:
        raw_text = open(args.text_file, "r", encoding="utf-8", errors="ignore").read()

    doc = DocumentInput(file_path=args.doc_file, raw_text=raw_text)
    svc = MetadataService(provider, Settings())
    res = svc.generate_metadata(doc, target_language=args.target_language)

    print("strategy_used:", res.strategy_used)
    if res.fallback_reason:
        print("fallback_reason:", res.fallback_reason)
    print(json.dumps(res.metadata, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()