from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

MetadataJSON = Dict[str, Any]

@dataclass
class DocumentInput:
    file_path: Optional[str] = None     # to attempt upload-first
    raw_text: Optional[str] = None      # required for chunked fallback
    filename_hint: Optional[str] = None
    use_ocr: bool = False               # use OCR instead of text extraction for PDFs
    ocr_languages: str = ""             # Tesseract language codes, e.g. "ukr+eng"

@dataclass
class MetadataResult:
    metadata: MetadataJSON
    strategy_used: str  # "upload" | "chunked"
    fallback_reason: Optional[str] = None
