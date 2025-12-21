# AI-book-translator — Architecture

## 1. Goals

**AI-book-translator** is a desktop application (PyQt5) that translates books (PDF/TXT/pasted text) into a user-selected target language using either:
- **Remote LLM via OpenAI-compatible API (API key + model name)**, or
- **Local LLM via an OpenAI-compatible endpoint (e.g., Ollama server URL + model name).**

This is not a “thin wrapper”: it performs **book metadata extraction + chapter-aware translation**, provides **progress tracking**, and supports **pause/continue with resumable state**.

---

## 2. High-level flow

### Step 0 — Model connection setup (UI Page 1)
User enters:
- **API key** (placeholder example: `sk-proj-kn...`)
- **Model name** (placeholder example: `gpt-5-nano`)
- OR a **local endpoint reference** (e.g., Ollama OpenAI-compatible base URL) + model name

App performs a **single check request**:
- If success → proceed to upload page
- If failure → stay on same page, show warning, ask to correct info

### Step 1 — Book metadata extraction (LLM → JSON)
User uploads a **PDF/TXT** or **pastes text** (UI Page 2), then app starts metadata generation (UI Page 3).

The LLM is asked to return **JSON** with:
- `"author(s)"`: extracted author name(s) OR `"not provided"`
- `"title"`: extracted title OR `"not provided"`
- `"language"`: detected language OR `"not provided"`
- `"summary"`: 1-paragraph summary OR `"not provided"`
- `"chapters"`: object where **keys are chapter identifiers** and **values are chapter summaries**
  - If chapters cannot be detected → `"chapters": "not provided"` (or `{}` depending on strict schema choice)

**Important rule:** if any field is missing in the document, the LLM must output `"not provided"` for that field.

Then the app **adds** (client-side) the selected target language into the resulting structure:
- `"target_language"`: value specified earlier in the UI

**Context forwarding rule into Step 2:**
- If at least one of `{author(s), title, current chapter description}` is available (not `"not provided"`), pass the available ones into Step 2 prompts.
- If *all* are `"not provided"`/None, Step 2 must **receive no arguments** from the preprocessing step (i.e., omit those fields entirely from the prompt).

### Step 2 — Chunk translation (1800 chars per chunk)
App extracts full text and splits it into blocks of **~1800 characters** (≈1 page).

For each chunk, app asks LLM to respond with **JSON only**:
```json
{
  "chapter": "<chapter detected OR previous chapter carried over>",
  "translation": "<translated text for this chunk>"
}
```

**Chapter tracking rule (stateful):**
- App stores a variable like `current_chapter`.
- Prompt includes prior chunk’s chapter; LLM may keep it or overwrite it if a new chapter begins.
- App updates `current_chapter` from the response after each chunk.

**Translation continuity rule (short context):**
- System prompt includes the **last 300 characters** of the **previous translation** so that translation style and context continue smoothly across chunks.

**No extra text rule:**
- LLM must output JSON only.
- The `"translation"` field must contain only translated text, without disclaimers, introductions, or summaries.

---

## 3. UI architecture (PyQt5 Pages)

### Page 1 — Model Setup
Inputs:
- API key
- model name
- optionally base URL (for local endpoint)

Behavior:
- “Test connection” is automatically triggered when user proceeds
- On success → open next page
- On failure → stay, show warning banner

### Page 2 — Book Input
Options:
- Upload PDF/TXT
- Paste text

Behavior:
- After input is provided → proceed to metadata generation page

### Page 3 — Metadata JSON Generation (Progress page)
Shows:
- progress indicator (spinner + stage text)

Remote/API LLM path:
- send the full extracted text (or a reasonable excerpt if you later add limits) to Step 1 prompt → get JSON

Local LLM path (iterative approach):
1) Chunk the book into pieces suitable for local context windows
2) Ask for a **very short summary per chunk**
   - For **one of the first few chunks**, explicitly ask it to:
     - include title/author if present
     - explicitly copy/provide the chapter list into the summary prompt
3) Ask for a **“summary of summaries”** in the **Step 1 JSON format**

On success:
- proceed to translation page and start automatically

### Page 4 — Translation Progress + Pause/Continue
On entry:
- translation starts automatically

Displays:
- percent progress: `translated_chunks / total_chunks * 100`

Controls:
- **Pause**
- **Continue**

When paused, app persists a resume state including:
- list of all chunks (or a reference to stored chunks)
- current chunk index
- prompt prepared for the current chunk (pre-send)
- previous chunk translation (needed for last-300 context rule)
- current chapter being processed

---

## 4. Core components

### 4.1 LLM Provider abstraction
A unified interface so UI/business logic never cares whether it’s OpenAI-hosted or local.

**Capabilities:**
- `test_connection()`
- `chat_json(system_prompt, user_prompt) -> dict` (strict JSON parse + retries)
- supports:
  - OpenAI API key authentication
  - configurable `base_url` for local endpoints (OpenAI-compatible)

### 4.2 Document ingestion
- PDF extraction (PDF → text)
- TXT reading
- direct pasted text

Output:
- `raw_text: str`

### 4.3 Chunking
- Step 2 chunking: fixed-length character chunks of **1800**
- Local metadata chunking: larger/smaller chunks tuned for local context window (configurable)

### 4.4 Prompt building
Two primary prompt “families”:

#### Metadata prompt (Step 1)
- input: full text (or local iterative flow’s summary-of-summaries input)
- output: strict JSON with required keys and `"not provided"` defaults

#### Translation prompt (Step 2)
- input: current chunk + optional metadata context + current chapter + last-300 previous translation
- output: strict JSON with `"chapter"` + `"translation"`

### 4.5 State management (pause/resume)
A serializable state object stored to disk (e.g., JSON file) containing:
- `chunks[]`
- `chunk_index`
- `current_chapter`
- `last_translation_tail_300`
- `current_prompt`
- `metadata_json`
- `target_language`

---

## 5. Data contracts (schemas)

### 5.1 Metadata JSON schema (Step 1)
Required keys:
- `author(s)` : string | array[string] | `"not provided"`
- `title` : string | `"not provided"`
- `language` : string | `"not provided"`
- `summary` : string | `"not provided"`
- `chapters` : object<string, string> | `"not provided"`
- `target_language` : string (added by the app after Step 1)

### 5.2 Translation JSON schema (Step 2)
```json
{
  "chapter": "string",
  "translation": "string"
}
```

---

## 6. Error handling & robustness

### Connection errors
- Page 1 must block navigation until `test_connection()` succeeds.

### Non-JSON model responses
- Strict parsing:
  - attempt to parse
  - if fails, auto-retry with a “Return valid JSON only” correction prompt (bounded retries)
- If still failing, surface an error in UI with actionable guidance.

### Rate limits / timeouts
- Use retry with exponential backoff for remote APIs.
- Allow pause/resume to avoid losing progress.

### PDF extraction failures
- Surface extraction error with suggestion to try TXT/paste.

---

## 7. Concurrency model (PyQt5)
Translation and metadata generation must run off the UI thread:
- Worker thread (QThread/QRunnable) does:
  - metadata generation
  - chunk translation loop
- UI receives signals:
  - progress updates
  - state updates (for pause/resume)
  - completion/failure

---

## 8. Proposed project structure

```text
ai-book-translator/
  ARCHITECTURE.MD
  README.md
  pyproject.toml
  .env.example

  src/
    ai_book_translator/
      main.py

      config/
        settings.py

      domain/
        models.py
        schemas.py

      infrastructure/
        llm/
          base.py
          openai_provider.py
          local_provider.py
          json_parser.py
        io/
          pdf_reader.py
          text_reader.py
        persistence/
          state_store.py
          paths.py

      services/
        connection_service.py
        metadata_service.py
        translation_service.py
        chunking.py
        prompt_builders.py

      ui/
        app_window.py
        pages/
          model_setup_page.py
          book_input_page.py
          metadata_page.py
          translate_page.py
        widgets/
          progress_widget.py
          error_banner.py
        workers/
          metadata_worker.py
          translation_worker.py

  tests/
    test_chunking.py
    test_json_parsing.py
    test_prompt_rules.py
```

---

## 9. Key implementation notes

- **All LLM calls** must go through `LLMProvider`.
- **Context rules** must be enforced by the prompt builder.
- **Pause/resume** must serialize enough state to restart safely.
- **Strict JSON** responses are mandatory; retries are required on violations.
