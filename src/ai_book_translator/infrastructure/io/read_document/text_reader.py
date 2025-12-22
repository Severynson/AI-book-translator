from __future__ import annotations

from pathlib import Path

from .base import ReadDocument


class TextReader(ReadDocument):
    @classmethod
    def supports(cls, path: str | Path) -> bool:
        return Path(path).suffix.lower() == ".txt"

    def read(self, path: str | Path) -> str:
        p = Path(path)
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            raise RuntimeError(f"Failed to read TXT file {p}: {e}") from e
