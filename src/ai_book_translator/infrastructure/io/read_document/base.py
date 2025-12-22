from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ReadDocument(ABC):
    """
    Abstract document reader.
    """

    @abstractmethod
    def read(self, path: str | Path) -> str:
        """Read document and return extracted text."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def supports(cls, path: str | Path) -> bool:
        """Return True if this reader supports the given file."""
        raise NotImplementedError

    @classmethod
    def from_path(cls, path: str | Path) -> "ReadDocument":
        """
        Factory method (Pythonic replacement for ReaderFactory).
        Chooses correct reader based on file extension.
        """
        from .pdf_reader import PdfReader
        from .text_reader import TextReader

        readers = [PdfReader, TextReader]

        for reader_cls in readers:
            if reader_cls.supports(path):
                return reader_cls()

        raise ValueError(f"No document reader for file: {path}")
