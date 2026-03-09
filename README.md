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
