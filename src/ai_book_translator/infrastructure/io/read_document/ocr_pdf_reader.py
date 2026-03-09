from __future__ import annotations

from pathlib import Path

from .base import ReadDocument


class OcrPdfReader(ReadDocument):
    """Reads PDF via Tesseract OCR (converts pages to images first)."""

    def __init__(self, languages: str = "eng"):
        self._languages = languages or "eng"

    @classmethod
    def supports(cls, path: str | Path) -> bool:
        return Path(path).suffix.lower() == ".pdf"

    def read(self, path: str | Path) -> str:
        import pytesseract
        from pdf2image import convert_from_path

        p = Path(path)

        try:
            images = convert_from_path(str(p))
            text_parts: list[str] = []

            for img in images:
                text = pytesseract.image_to_string(img, lang=self._languages)
                if text and text.strip():
                    text_parts.append(text)

            return "\n".join(text_parts)

        except FileNotFoundError:
            raise RuntimeError(f"PDF file not found: {p}")
        except Exception as e:
            raise RuntimeError(f"Error OCR-reading PDF {p}: {e}") from e
