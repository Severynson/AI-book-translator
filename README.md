# ai-book-translator (skeleton)

Implements **Option A** for Step 1 metadata generation:

1) Try **document upload** (single call) first  
2) If it fails (unsupported or upload failed), **fallback to chunked summarization** → summary-of-summaries → metadata JSON

Includes:
- strict JSON parsing + repair retries
- OpenAI-compatible provider abstraction
- chunking utilities + prompt builders
- MetadataService with upload-first fallback logic

> Note: The OpenAI-compatible provider is a generic skeleton. Adapt endpoints/payloads to your specific API (OpenAI, Azure, Ollama OpenAI-compat, etc.).
