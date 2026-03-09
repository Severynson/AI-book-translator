# Refactoring Plan: Remove Redundancy and Cleanly Support Multiple LLM Backends

## 1. Why this plan exists

Your current architecture already has the right intent (provider abstraction), but responsibilities are split across UI, workers, services, and providers in a way that causes duplication and provider-specific leakage.

The main goal of this refactor is to make **one clean LLM interface** the single integration point for both:

- frontier models via API key
- local models via OpenAI-compatible endpoint (Ollama)

This document is intentionally implementation-ready, but it does **not** implement changes.

---

## 1.1 Hard requirement: interruption-safe resume

Translation must be resumable after:

- API-side errors (5xx, 429, temporary failures)
- model refusals
- internet/network interruptions
- app/process crash during long runs

The system must preserve:

- all already translated content
- exact resume position (`next_chunk_index`)
- all context needed to continue with the same prompt state (`current_chapter`, previous-tail context, model config snapshot)

Resume behavior target:

- on restart, user can continue from exactly the first not-yet-committed chunk.
- We want to change the order of 1st and 2nd UI screens - now at first we want to ask information about the document /text copied to the textbox field user wants to translate (it was screen 2 until this point, now should be the 1st). In case if files preserving state of interupted translation of this file exist - a pop-up window has to be displayed to the user, reminding that translation of this document was interupted the last time, and user has to be asked if they want to proceed with translation of this text, or start again with new settings. [Text explaining the situation, asking this, and 2 Buttons: "Continue", and "Start over", will be displayed at the end]. In case if the user select "Start over" - we delete the file storing the state of interupted translation, creating a new one instead, as the user prohress to the next page. Or in case if they select continue - the following screen (currently the 1st, now has to be done the 2nd) shouldn't ask to specify LLM settings for translation (and must not appear at all if we select to continue translation, but not starting over with a new document/text), but old settings shouold be used. Refactor the translation metadata and LLM configs page (e.g. page asking target language, sequence enth for translation for 1 chunk), so it would save configs for the translation in a JSON document (I guess already existing JSON which stores metadata of the text/file we want to translate can be used again to store some new info, such as LLM chunk length usage for translation), so it would be possible to load it later, while proceeding interupted translation. This config JSON has to be linked to the translated text document's ID)
  P.S. Make sure that path stored in metadata JSONs is absolute, so even if the doc to translate is in downloads - it could be easily loaded again using absolute path to continue translation.
- no silent data loss.
- IMPORTANT: no duplicated chunk output in final document! Make sure to avoid this bug!

---

## 2. What is currently redundant or messy

### 2.1 Provider-specific behavior leaks outside provider layer

- `MetadataService` sends OpenAI Responses-specific options (`text.format`, `max_output_tokens`) directly through provider calls.
- `MetadataService` uses exceptions (`UploadNotSupportedError`) as capability detection.
- Local and remote differences are partially encapsulated, partially leaked.

Impact:

- Service layer knows too much about backend API dialect.
- Adding a third backend will increase branching and duplication.

### 2.2 Translation logic is in UI worker, not service layer

- `src/ai_book_translator/services/translation_service.py` is empty.
- Core translation orchestration exists in `ui/workers/translation_worker.py`.

Impact:

- Business logic coupled to UI threading and Qt signals.
- Harder to test; logic duplicates with metadata service style.

### 2.3 Repeated “provider construction” logic

- UI model setup creates providers directly with `if provider == openai else ollama`.
- Similar provider selection logic exists in `experiments/*` scripts.

Impact:

- Configuration and validation rules are duplicated.
- Easy for defaults to drift.

### 2.4 Repeated document extraction and hashing logic

- Document text extraction is repeated in:
  - `AppWindow._on_document_ready`
  - `MetadataWorker.run`
  - `TranslatePage.start`
- Document hash exists in both `_doc_hash_from_text` and `compute_document_hash`.

Impact:

- Multiple places to maintain for same behavior.
- Potentially inconsistent text used for metadata/translation/resume identity.

### 2.5 Repeated JSON handling and retry strategy

- JSON parse/repair logic is split between `services/llm_json.py` and metadata service upload flow.
- Retry logic exists in both provider (`OpenAIResponsesProvider._post_json`) and service (`upload_retries` loop).
- Local provider has much weaker retry behavior than OpenAI provider.

Impact:

- Inconsistent reliability and hidden retry amplification.
- Hard to reason about failure semantics.

### 2.6 Resume/state handling exists but is not a formal contract

- Current translation flow already saves preflight state and per-chunk state updates.
- But state semantics are tightly coupled to worker flow and not defined as a strict, testable checkpoint protocol.
- Recovery correctness is not documented as a consistency model (write ordering, idempotency, crash boundaries).

Impact:

- Resume may work in common cases but is harder to prove correct under edge failures.
- Future refactors risk breaking recovery guarantees.

### 2.7 Architectural drift / stale artifacts

- `translation_service.py` is empty (expected core service missing).
- `ConnectionWorker` exists but appears unused.
- `state_store.py` overlaps with `translation_state.py` but is not integrated.
- Debug prints remain in prompt builder (`print(...)` in `build_translation_user_prompt`).
- README run command points to `ai_book_translator.ui.main`, but entrypoint is `ai_book_translator.main`.
- ARCHITECTURE says translation chunk is ~1800 chars, runtime default is 30000.

Impact:

- Harder onboarding and confidence in system shape.

---

## 3. Target architecture (clean separation)

Use four layers:

1. **UI Layer**

- Collects user input and displays progress.
- Starts workers, does not contain business logic.

2. **Application Services Layer**

- `ConnectionService`, `MetadataService`, `TranslationService` orchestrate workflows.
- Depends only on unified LLM client interfaces.

3. **LLM Core Layer**

- A provider-agnostic client API with typed requests/responses.
- Handles capabilities, retries, JSON/schema enforcement strategy.

4. **Provider Adapters Layer**

- OpenAI adapter, Ollama adapter.
- Only place that knows endpoint shape (`/v1/responses` vs `/v1/chat/completions`, file upload, etc).

This isolates differences where they belong.

---

## 4. Proposed unified LLM interface

Create typed models and one narrow interface.

```python
# illustrative shape
@dataclass(frozen=True)
class LLMCapabilities:
    supports_file_upload: bool
    supports_json_schema: bool

@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    user_prompt: str
    file_path: str | None = None
    json_schema: dict[str, Any] | None = None
    max_tokens: int | None = None
    temperature: float | None = None

@dataclass(frozen=True)
class LLMResponse:
    text: str
    raw: dict[str, Any] | None = None

class LLMClient(Protocol):
    def capabilities(self) -> LLMCapabilities: ...
    def test_connection(self) -> None: ...
    def generate_text(self, request: LLMRequest) -> LLMResponse: ...
```

Important rules:

- `max_tokens` is canonical in services; adapters translate to backend-specific fields (`max_output_tokens` for Responses API).
- `json_schema` is optional, backend may ignore if unsupported.
- `file_path` support is explicit via capabilities; avoid exception-driven control flow for feature detection.

---

## 5. Where each responsibility should move

### 5.1 Move API-dialect logic into provider adapters

Keep only request translation + HTTP behavior in:

- `infrastructure/llm/providers/openai_responses_adapter.py`
- `infrastructure/llm/providers/ollama_chat_adapter.py`

Do not keep metadata-specific logic there.

### 5.2 Introduce an LLM orchestration utility for JSON reliability

Add service-level helper (or dedicated component) to centralize:

- strict JSON parse
- loose extraction fallback
- repair prompt retries
- optional schema-first attempt when capability exists

Example component:

- `services/llm_json_client.py` with methods:
  - `generate_json(request, repair_retries, schema=None)`

This removes JSON-handling duplication from metadata and translation flows.

### 5.3 Move translation orchestration into `TranslationService`

`TranslationWorker` should only:

- call `TranslationService.translate(...)`
- emit progress from callbacks/events

`TranslationService` should own:

- chunking
- chapter state updates
- prompt build
- JSON parse/repair
- output append
- state persistence semantics

### 5.4 Centralize provider construction in one factory

Add:

- `domain/models.py` or new `domain/llm_config.py` for typed config
- `infrastructure/llm/provider_factory.py`

UI should create config, not provider objects directly.

### 5.5 Centralize document loading

Add `DocumentService` (or utility) with single method:

- `ensure_raw_text(document_input) -> DocumentInput`

Use it in app window and workers instead of repeating extraction logic.

### 5.6 Introduce explicit checkpoint/resume contract

Define a dedicated translation state contract owned by `TranslationService` (not UI worker):

- durable checkpoint model
- commit ordering rules
- deterministic recovery algorithm
- compatibility/versioning for state schema

---

## 6. Concrete file-by-file refactor plan

### Phase 0: Lock down resume semantics first (before major architecture moves)

1. Define `TranslationCheckpoint` schema in a dedicated module (e.g. `domain/translation_checkpoint.py`):

- `schema_version`
- `document_hash`
- `target_language`
- `provider_fingerprint` (provider type/base_url/model)
- `next_chunk_index`
- `chunks_total`
- `current_chapter`
- `previous_tail`
- `output_mode` metadata (single-file or chunk-files)
- `updated_at_unix`
- optional `last_error` snapshot for diagnostics

2. Define checkpointing invariants:

- `next_chunk_index` always means “first chunk not yet committed”
- only committed chunks are considered done
- checkpoint writes are atomic (`tmp` + replace)

3. Define crash-safe commit order for each chunk:

- call LLM
- validate response JSON
- persist translated content for chunk
- fsync/flush content
- atomically update checkpoint (`next_chunk_index = i + 1`)

4. Add recovery algorithm:

- load checkpoint by `document_hash`
- verify provider/model compatibility (warn on mismatch)
- resume from `next_chunk_index`
- preserve already translated content exactly as committed

Deliverable: resume behavior is explicitly defined and testable before broader refactor.

### Phase 0.1 (recommended): store per-chunk output files for strong idempotency

To guarantee exact resume with no duplication in crash windows, prefer:

- `state/translation_runs/<run_id>/chunks/<index>.txt` per translated chunk
- checkpoint tracks committed chunk count/index
- final merged output is generated by ordered concatenation of chunk files

Why:

- each committed chunk is atomic and independently verifiable
- avoids duplicate-append edge cases in monolithic output files
- recovery can trust filesystem presence of chunk artifacts

If keeping monolithic output, add output offset/hash ledger to detect duplicate writes on resume.

### Phase 1: Introduce new abstractions without breaking old flow

1. Add `src/ai_book_translator/infrastructure/llm/types.py`

- `LLMCapabilities`, `LLMRequest`, `LLMResponse`

2. Add `src/ai_book_translator/infrastructure/llm/client.py`

- new protocol/ABC for unified client interface

3. Add `src/ai_book_translator/infrastructure/llm/provider_factory.py`

- build client from typed config

4. Add `src/ai_book_translator/domain/llm_config.py`

- `OpenAIConfig`, `OllamaConfig`, union type

5. Keep existing providers temporarily; adapt them to implement new client interface.

Deliverable: old code still works, new interface available.

### Phase 2: Unify JSON generation behavior

1. Add `src/ai_book_translator/services/llm_json_client.py`

- one path for schema attempt + parse + repair

2. Refactor `MetadataService` to use this helper.

- Remove direct backend-specific kwargs from metadata service.
- Replace exception-based upload capability detection with `client.capabilities().supports_file_upload`.

3. Keep existing behavior parity:

- upload-first
- chunked fallback
- retries
- schema validation and normalization

Deliverable: Metadata flow becomes provider-agnostic.

### Phase 3: Move translation logic out of UI worker

1. Implement `src/ai_book_translator/services/translation_service.py`.

- Accept callbacks for progress/chunk events.
- Keep persistence and resume rules identical first.
- Implement checkpoint contract from Phase 0 as service-owned behavior.

2. Thin `ui/workers/translation_worker.py` to orchestration wrapper around service.

3. Add translation output schema validator for `{"chapter": str, "translation": str}`.

Deliverable: Business logic testable without Qt.

### Phase 4: Remove duplicate setup/extraction logic

1. Refactor `ui/pages/model_setup_page.py`

- Build `LLMConfig` only.
- Call `ProviderFactory.create(config)`.

2. Decide one connection test path:

- either synchronous in UI or use `ConnectionWorker`.
- Prefer `ConnectionWorker` to avoid UI blocking.

3. Add `services/document_service.py` to centralize `raw_text` extraction.

- Replace duplicated extraction in AppWindow/MetadataWorker/TranslatePage.

4. Replace `_doc_hash_from_text` with `compute_document_hash` everywhere.

Deliverable: shared behavior in one place.

### Phase 5: Cleanup and consistency

1. Remove or integrate dead modules:

- `state_store.py` (if redundant)
- unused worker(s)
- stale experiments imports (`local_ollama_provider` typo)

2. Remove debug prints from prompt builders.

3. Align docs and runtime:

- README entry command
- ARCHITECTURE chunk-size defaults vs actual settings

Deliverable: reduced drift and clearer maintenance.

---

## 7. Suggested module structure after refactor

```text
src/ai_book_translator/
  domain/
    llm_config.py
    models.py
    schemas.py
  infrastructure/
    llm/
      client.py
      types.py
      provider_factory.py
      providers/
        openai_responses_adapter.py
        ollama_chat_adapter.py
      exceptions.py
      json_parser.py
    io/
      read_document/...
    persistence/...
  services/
    connection_service.py
    document_service.py
    llm_json_client.py
    metadata_service.py
    translation_service.py
    prompts.py
  ui/
    pages/...
    workers/...
```

---

## 8. Testing strategy for safe migration

### 8.1 Unit tests to add first

1. `tests/test_llm_factory.py`

- config -> correct provider adapter
- config validation failures

2. `tests/test_llm_json_client.py`

- valid JSON first pass
- loose extraction path
- repair retry success/failure
- schema-supported vs unsupported backends

3. `tests/test_translation_service.py`

- chapter carry-over behavior
- resume from chunk index
- output append and state updates
- recovery after simulated crash between chunk commit steps
- resume after transient API/network error
- resume after refusal on chunk N, then successful retry
- checkpoint schema backward compatibility (if versioned)

4. `tests/test_document_service.py`

- file/paste paths
- OCR flags passthrough

### 8.2 Regression tests to preserve behavior

- keep existing metadata tests, adapt stubs to new interfaces
- add one integration smoke per provider for `test_connection` + `generate_text`

---

## 9. Migration safety rules

1. Keep old interfaces until new ones are fully wired.
2. Migrate one service at a time (metadata first, translation second).
3. Do not combine architectural refactor with prompt rewrites in same PR.
4. Introduce feature flags or compatibility adapters when replacing provider calls.

---

## 10. Priority order (recommended execution)

1. Introduce typed LLM interface + factory (no behavior change).
2. Centralize JSON generation/repair strategy.
3. Move translation orchestration into service.
4. Deduplicate document extraction and hashing.
5. Remove dead code and align docs.

This order minimizes risk and gives immediate structural wins on the exact pain point: multi-LLM support.

---

## 11. Definition of done for this refactor

You can consider this refactor complete when:

1. Services no longer pass backend-specific kwargs (`text.format`, `max_output_tokens` mapping logic) directly.
2. Provider capability checks are explicit (no control flow based on upload exception for normal branching).
3. `translation_service.py` contains the translation workflow; worker is thin.
4. Provider construction exists in exactly one place (factory).
5. Document extraction is centralized and reused.
6. Docs match runtime behavior.
7. Translation resume is deterministic and interruption-safe, with tested checkpoint semantics.

---

## 12. Notes about non-goals

- This plan does not change prompts or translation quality policy by default.
- This plan does not require changing persistence format immediately (unless you choose to during Phase 3+).
- This plan does not remove support for either OpenAI or Ollama; it formalizes both under a cleaner interface.
