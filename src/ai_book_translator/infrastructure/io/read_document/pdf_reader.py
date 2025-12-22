from __future__ import annotations

from pathlib import Path
from pypdf import PdfReader as PyPdfReader

from .base import ReadDocument


class PdfReader(ReadDocument):
    @classmethod
    def supports(cls, path: str | Path) -> bool:
        return Path(path).suffix.lower() == ".pdf"

    def read(self, path: str | Path) -> str:
        p = Path(path)

        try:
            reader = PyPdfReader(p)
            text_parts: list[str] = []

            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

            return "\n".join(text_parts)

        except FileNotFoundError:
            raise RuntimeError(f"PDF file not found: {p}")
        except Exception as e:
            raise RuntimeError(f"Error reading PDF {p}: {e}") from e
