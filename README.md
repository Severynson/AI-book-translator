# AI-book-translator

**AI-book-translator** is a desktop application (PyQt5) that translates books (PDF/TXT/pasted text) into a user-selected target language using either:
- **Remote LLM via OpenAI-compatible API** (API key + model name), or
- **Local LLM via an OpenAI-compatible endpoint** (e.g., Ollama server URL + model name)

It performs **book metadata extraction + chapter-aware translation**, provides **progress tracking**, and supports **pause/continue with resumable state**.

---

## Quick Start

### 1. System Dependencies

#### macOS (using Homebrew)
```bash
brew install tesseract
brew install tesseract-lang  # for language data (includes Ukrainian)
brew install poppler
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
sudo apt-get install tesseract-ocr-ukr  # for Ukrainian language
sudo apt-get install poppler-utils
```

#### Windows
1. **Tesseract**: Download installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
   - Run the installer and note the installation path (e.g., `C:\Program Files\Tesseract-OCR`)
   - Add to system PATH or set `PYTESSERACT_PATH` environment variable

2. **Poppler**: Download from [oschwartz10612/poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases/)
   - Extract and add the `bin` folder to system PATH

### 2. Create Virtual Environment

#### Using `venv` (Python 3.10+)
```bash
python3 -m venv venv
source venv/bin/activate    # macOS/Linux
# or
venv\Scripts\activate       # Windows
```

#### Using `conda`
```bash
conda create -n ai-book-translator python=3.10
conda activate ai-book-translator
```

### 3. Install Python Dependencies
```bash
pip install -e .
```

Or install manually:
```bash
pip install requests>=2.31.0 pypdf reportlab pytesseract>=0.3.10 pdf2image>=1.16.3 Pillow>=10.0.0
```

### 4. Run the Application
```bash
python src/ai_book_translator/main.py
```

---

## Features

- **PDF/TXT Upload or Pasted Text** — Choose your input method
- **OCR for Scanned PDFs** — Use Tesseract OCR with configurable language detection (e.g., Ukrainian + English)
- **Automatic Metadata Extraction** — Title, author(s), language(s), summary, chapter list
- **Chapter-Aware Translation** — Preserves chapter structure and detects chapter boundaries
- **Secondary Language Preservation** — Phrases in secondary languages (Latin, English in Ukrainian texts, etc.) are NOT translated
- **Pause & Resume** — Pause translation at any time and resume later without losing progress
- **Progress Tracking** — Real-time progress indicator during metadata and translation phases

## Planned Translation Continuity Features

The following translation-resume features are planned but not yet implemented:

- **Chunk Boundary Sentence Safety** — Chunking already prefers to split on natural boundaries before the configured size limit, walking backward to punctuation/newline/space boundaries when possible. Planned work extends this by making the model explicitly avoid "finishing" an incomplete last sentence and by making the next chunk translation aware that it may begin with a continuation of the previous sentence.
- **Cross-Chunk Repair Signaling** — The model should be allowed to explicitly react to both cases: an obviously interrupted last sentence, and a previous-chunk tail that was translated badly and should be replaced. For models that support structured output, this should be returned as JSON. For models that do not expose a strict JSON API mode, the system should still instruct them to return JSON and try to recover it through parsing/repair before falling back to a deterministic text-marker format.
- **Per-Translation Custom Instructions** — Each translation run should be able to store user-defined instructions in the translation-state JSON and inject them into every translation request. This is intended for non-standard workflows such as modernization, historical-language normalization, or other text-specific handling rules.
- **Prompt Customization Persistence** — The translation-state JSON should preserve both system-prompt customization and per-run user instructions so interrupted translations can resume with exactly the same prompt behavior.
- **LLM-Assisted Error Explanation for User-Fixable Cases** — If a translation error looks potentially fixable by adjusting the prompt, the application should be able to ask an LLM to explain the error in plain language and suggest an extra system-prompt addition the user may approve, reject, or replace with their own instruction. Clearly internal/code errors should continue to use normal error handling without an LLM popup.

---

## Project Structure

```
ai-book-translator/
├── README.md
├── ARCHITECTURE.MD
├── pyproject.toml
└── src/
    └── ai_book_translator/
        ├── config/              # Settings and configuration
        ├── domain/              # Data models and schemas
        ├── infrastructure/      # LLM providers, document readers, persistence
        ├── services/            # Business logic (metadata, translation, prompts, chunking)
        ├── ui/                  # PyQt5 pages, workers, widgets
        └── main.py
```

---

## Configuration

Edit `src/ai_book_translator/config/settings.py` to adjust:
- `translation_chunk_chars` — Characters per chunk (default: 30000)
- `local_metadata_chunk_chars` — Chunk size for local LLM metadata generation (default: 8000)
- `upload_retries` — Retry count for API uploads (default: 2)
- `json_repair_retries` — JSON repair attempts (default: 2)

---

## Development

### Run Tests
```bash
pytest tests/
```

---

## Requirements

- Python 3.10+
- PyQt5
- Tesseract OCR (system dependency)
- Poppler (system dependency, for PDF-to-image conversion)
- OpenAI API key or local Ollama instance

See [ARCHITECTURE.MD](ARCHITECTURE.MD) for detailed technical documentation.
