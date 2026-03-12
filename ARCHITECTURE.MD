# AI-book-translator — Architecture

## 1. Goals

**AI-book-translator** is a desktop application (PyQt5) that translates books (PDF/TXT/pasted text) into a user-selected target language using either:
- **Remote LLM via OpenAI-compatible API (API key + model name)**, or
- **Local LLM via an OpenAI-compatible endpoint (e.g., Ollama server URL + model name).**

This is not a "thin wrapper": it performs **book metadata extraction + chapter-aware translation**, provides **progress tracking**, supports **pause/continue with resumable state**, and handles **chunk boundary repair** for seamless translations.

---

## 2. High-level flow

### Step 1 — Book Input (UI Page 1)
User uploads a **PDF/TXT** or **pastes text**.

**OCR controls** (visible when "Upload PDF/TXT" is selected):
- Checkbox: **"Use OCR (for scanned PDFs)"** — toggles between text extraction (default) and OCR
- Text input: **OCR languages** — Tesseract language codes, primary first (e.g., `ukr+eng`)

**Resume detection:**
- If an incomplete translation checkpoint exists for this document (matched by content hash), a popup asks **"Continue"** or **"Start over"**.
- **Continue**: skips model setup, restores saved LLM config + custom instructions, resumes from last committed chunk.
- **Start over**: deletes old checkpoint, proceeds with fresh flow.

### Step 2 — Model Setup (UI Page 2)
User enters:
- **Provider**: OpenAI or Ollama
- **API key** (OpenAI) or **base URL** (Ollama) + **model name**
- **Target language**
- **Chunk size** (chars per translation chunk, default 30000)
- **System prompt customization** (optional, persisted for resume)
- **Translation instruction** (optional per-run instruction, persisted for resume)

App performs a **connection test**:
- If success → proceed
- If failure → stay on same page, show warning

### Step 3 — Book metadata extraction (LLM → JSON, UI Page 3)
The LLM returns **JSON** with:
- `"author(s)"`: extracted author name(s) OR `"not provided"`
- `"title"`: extracted title OR `"not provided"`
- `"language"`: array of detected languages, ordered by frequency (primary first)
- `"summary"`: 1-paragraph summary OR `"not provided"`
- `"chapters"`: object with `"general"` and `"detailed"` summaries per chapter

Then the app **adds** (client-side):
- `"target_language"`: value specified in Step 2

**Context forwarding into Step 4:**
- Available metadata fields (title, author, chapter descriptions, language array) are passed to translation prompts.

### Step 4 — Chunk translation (UI Page 4)
App extracts full text and splits into chunks (configurable size, default ~30000 chars).

For each chunk, app asks LLM to respond with **JSON only**:
```json
{
  "chapter": "<chapter detected OR previous chapter carried over>",
  "translation": "<translated text for this chunk>",
  "tail_status": "clean | possibly_truncated",
  "repair_previous_fragment": "(optional) old trailing fragment to replace",
  "repair_retranslation": "(optional) corrected translation for that fragment"
}
```

**Chapter tracking rule (stateful):**
- App stores `current_chapter`, updated from each response.
- The LLM is trusted to detect chapter transitions in the text.
- When the LLM returns a chapter name, it is fuzzy-matched against metadata chapter keys using `find_matching_chapter_key()`. This handles: case differences, Roman vs Arabic numerals (e.g., "Chapter II" matches "Chapter 2"), and common chapter prefixes in multiple languages (Chapter, Rozdil, Kapitel, Chapitre, Glava, Capitolo, etc.).
- If a match is found, the **metadata key** is used as `current_chapter` (so the next chunk's prompt loads the correct detailed description). If no match is found, the LLM's raw chapter name is used as-is.

**Translation continuity rule (short context):**
- System prompt includes the **last 300 characters** of the **previous source chunk** for context.

**Chunk boundary rules:**
- If the current chunk ends with an incomplete sentence, the model translates only what is present (no guessing). Sets `tail_status` to `"possibly_truncated"`.
- Next chunk receives previous-tail context; model continues from the sentence continuation point.
- If the model detects the previous chunk's ending was translated poorly, it can provide `repair_previous_fragment` (exact old text to remove) and `repair_retranslation` (corrected replacement). The service applies this repair before appending the current chunk.

**Secondary language preservation rule:**
- If the metadata `"language"` array contains more than one element, the translation prompt instructs the LLM to **preserve secondary-language phrases as-is**.
- Example: `"contra spem spero"` (Latin) should not be translated if Latin is a secondary language.

**Custom instructions:**
- `system_prompt_customization`: appended to the system prompt for all chunks.
- `translation_instruction`: included in the user prompt per chunk.
- Both are persisted in the checkpoint for resume.

---

## 3. Layered architecture

### 3.1 UI Layer
- Collects user input and displays progress.
- Starts workers, does not contain business logic.
- Error popup for prompt-fixable translation failures (LLM-assisted guidance).

### 3.2 Application Services Layer
- `ConnectionService`: tests LLM connectivity.
- `MetadataService`: orchestrates metadata extraction (upload-first with chunked fallback).
- `TranslationService`: owns complete translation workflow — chunking, prompt building, JSON parse/repair, boundary repair, checkpoint persistence, error classification.
- `DocumentService`: centralized text extraction and hashing.
- `LLMJsonClient`: unified JSON generation with schema-first → prompt-enforced → repair loop.

### 3.3 LLM Core Layer
- `LLMClient` (Protocol): provider-agnostic interface with `capabilities()`, `test_connection()`, `generate_text(request)`.
- `LLMCapabilities`: declares `supports_file_upload` and `supports_json_schema`.
- `LLMRequest` / `LLMResponse`: typed request/response models.
- Services use `max_tokens` canonically; adapters translate to backend-specific fields.

### 3.4 Provider Adapters Layer
- `OpenAIResponsesAdapter`: uses `/v1/responses` (supports file upload + JSON schema).
- `OllamaChatAdapter`: uses `/v1/chat/completions` (no upload, no schema).
- Only place that knows endpoint shape and API dialect.

---

## 4. UI architecture (PyQt5 Pages)

### Page 1 — Book Input
- Upload PDF/TXT or paste text
- OCR checkbox + language codes for scanned PDFs
- Resume detection: popup if incomplete translation found

### Page 2 — Model Setup
- Provider selector (OpenAI / Ollama)
- API key / base URL + model name
- Target language, chunk size
- System prompt customization (optional)
- Translation instruction (optional)
- Connection test on proceed

### Page 3 — Metadata Generation (Progress)
- Spinner + stage text
- Remote: upload full text, get JSON
- Local: chunk summaries → summary-of-summaries → JSON
- On success → auto-proceed to translation

### Page 4 — Translation Progress + Pause/Continue
- Auto-starts translation
- Progress bar + stage text
- Streaming output preview
- Pause / Continue controls
- LLM-assisted error popup for prompt-fixable failures

---

## 5. Core components

### 5.1 LLM Client Protocol
```python
class LLMClient(Protocol):
    def capabilities(self) -> LLMCapabilities: ...
    def test_connection(self) -> None: ...
    def generate_text(self, request: LLMRequest) -> LLMResponse: ...
```

Provider construction: `create_client(config: LLMConfig) -> LLMClient` via factory.

### 5.2 Document ingestion
- **PDF text extraction** (PDF → text via `pypdf`)
- **PDF OCR extraction** (PDF → images via `pdf2image` → text via `pytesseract`/Tesseract OCR)
- TXT reading
- Direct pasted text

**OCR mode** (user-selectable on Page 1):
- Uses **Tesseract OCR** with configurable language codes (e.g., `ukr+eng`)
- Requires system dependencies: `tesseract` and `poppler`

### 5.3 Chunking
- Translation chunking: configurable character chunks (default 30000)
- Local metadata chunking: smaller chunks tuned for local context windows (configurable)

### 5.4 Prompt building
Two primary prompt families:

#### Metadata prompt (Step 3)
- input: full text (or local flow's summary-of-summaries)
- output: strict JSON with required keys and `"not provided"` defaults

#### Translation prompt (Step 4)
- input: current chunk + metadata context + current chapter + last-300 source tail + custom instructions
- output: strict JSON with chapter, translation, tail_status, optional repair fields
- secondary language preservation when detected in metadata

### 5.5 State management (checkpoint/resume)
`TranslationCheckpoint` dataclass persisted as JSON:
- `schema_version`: checkpoint format version (currently 2)
- `document_hash`: content hash for identity
- `document_path`: absolute path (empty for pasted text)
- `target_language`
- `llm_config`: serialized LLM provider config for reconstruction on resume
- `next_chunk_index`: first chunk NOT yet committed
- `chunks_total`
- `current_chapter`
- `previous_tail`: last 300 chars of source text
- `output_txt_path`: absolute path to output file
- `metadata_path`: absolute path to cached metadata JSON
- `translation_chunk_chars`
- `system_prompt_customization`: persisted custom system prompt additions
- `translation_instruction`: persisted per-run translation instruction
- `boundary_repair_marker`: deterministic fallback marker
- `last_committed_chunk_tail_translation`: translated tail for boundary repair
- `last_committed_chunk_tail_status`: `clean` | `possibly_truncated` | `repaired`
- `last_error`: diagnostic snapshot
- `updated_at_unix`

**Checkpointing invariants:**
- `next_chunk_index` always means "first chunk not yet committed"
- Checkpoint writes are atomic (tmp + replace)
- Crash-safe commit order: LLM call → validate → append output → flush → update checkpoint

### 5.6 Error classification and LLM-assisted recovery
Errors are classified into categories:
- `transient_provider_error`: timeouts, rate limits, 5xx — retry recommended
- `invalid_model_output`: unparseable response
- `prompt_fixable_output_error`: may be fixable by changing prompt instructions
- `content_policy_or_refusal`: model refused content
- `internal_code_error`: non-recoverable internal failure

For prompt-fixable errors:
1. TranslationService calls an explanatory LLM prompt
2. Returns structured payload: `user_explanation`, `likely_cause`, `suggest_prompt_patch`, `confidence_can_be_fixed_with_prompt`
3. UI shows popup: user can approve, edit, or reject the suggested fix
4. Approved patches are persisted in checkpoint before retry
5. Internal/code errors bypass this flow entirely

---

## 6. Data contracts (schemas)

### 6.1 Metadata JSON schema (Step 3)
Required keys:
- `author(s)` : string | `"not provided"`
- `title` : string | `"not provided"`
- `language` : array[string] | `["not provided"]` — **ordered by frequency** (primary first)
- `summary` : string | `"not provided"`
- `chapters` : object<string, object> | `{}` — each value has `"general"` and `"detailed"` keys
- `target_language` : string (added by app)

**Language array convention:**
- First element = **primary language** (translate FROM)
- Subsequent elements = **secondary languages** (intentionally untranslated by original author)
- Example: `["Ukrainian", "English", "Latin"]`

### 6.2 Translation JSON schema (Step 4)
```json
{
  "chapter": "string",
  "translation": "string",
  "tail_status": "clean | possibly_truncated",
  "repair_previous_fragment": "(optional) string",
  "repair_retranslation": "(optional) string"
}
```

---

## 7. Error handling & robustness

### Connection errors
- Page 2 blocks navigation until `test_connection()` succeeds.

### Non-JSON model responses
- Strategy: schema-enforced (if supported) → prompt-enforced → strict parse → loose extraction → repair loop (bounded retries).
- If still failing, classify error and optionally offer LLM-assisted popup.

### Rate limits / timeouts
- Retry with exponential backoff for remote APIs.
- Pause/resume to avoid losing progress.

### Chunk boundary errors
- Repair protocol handles incomplete sentences at chunk boundaries.
- No duplicate output: repair replaces targeted fragment, does not append.
- Ambiguous repair target fails safely (skips repair).

### PDF extraction failures
- Surface extraction error with suggestion to try TXT/paste.

---

## 8. Concurrency model (PyQt5)
Translation and metadata generation run off the UI thread:
- Worker thread (QThread) calls service layer.
- UI receives signals: progress, chunk_done, success, failure, error_popup.
- Error popup uses mutex + wait condition to synchronize worker thread with UI dialog.

---

## 9. Project structure

```text
src/ai_book_translator/
  main.py
  config/
    settings.py
  domain/
    llm_config.py          # OpenAIConfig, OllamaConfig, LLMConfig union
    models.py              # DocumentInput, MetadataResult
    schemas.py             # validate_metadata_json, normalize_not_provided
    translation_checkpoint.py  # TranslationCheckpoint dataclass
  infrastructure/
    llm/
      client.py            # LLMClient Protocol
      types.py             # LLMCapabilities, LLMRequest, LLMResponse
      provider_factory.py  # create_client(config) factory
      exceptions.py        # Error classes + classify_error()
      json_parser.py       # parse_json_strict, extract_json_object_loose
      base.py              # backward-compat shim
      providers/
        openai_responses_adapter.py
        ollama_chat_adapter.py
      openai_provider.py   # legacy, still functional
      local_provider.py    # legacy, still functional
    io/
      read_document/
        base.py            # ReadDocument ABC + from_path factory
        pdf_reader.py
        ocr_pdf_reader.py  # Tesseract OCR via pytesseract + pdf2image
        text_reader.py
    persistence/
      metadata_cache.py
      translation_state.py
  services/
    connection_service.py
    document_service.py    # ensure_raw_text, document_hash
    llm_json_client.py     # LLMJsonClient (schema → prompt → repair)
    metadata_service.py
    translation_service.py # TranslationService + ErrorPopupPayload
    chunking.py
    prompts.py             # All prompt builders
    llm_json.py            # backward-compat
  ui/
    app_window.py          # AppWindow + AppState + resume logic
    pages/
      book_input_page.py   # Page 1
      model_setup_page.py  # Page 2 (+ custom instruction fields)
      metadata_page.py     # Page 3
      translate_page.py    # Page 4 (+ error popup handling)
    widgets/
      error_banner.py
    workers/
      metadata_worker.py
      translation_worker.py  # Thin wrapper + error popup signal
```

---

## 10. Key implementation notes

- **All LLM calls** go through the `LLMClient` protocol.
- **Provider-specific details** are isolated in adapter classes — services never pass backend-specific kwargs.
- **Capability detection** uses `client.capabilities()` — no exception-based control flow.
- **Context rules** are enforced by the prompt builder.
- **Pause/resume** serializes full state including LLM config and custom instructions.
- **Strict JSON** responses are mandatory; schema → prompt → repair fallback chain.
- **Boundary repair** prevents incomplete sentence artifacts without duplicating output.
- **Error classification** routes prompt-fixable failures to LLM-assisted popup; internal errors bypass it.
