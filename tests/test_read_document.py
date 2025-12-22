import pytest
from pathlib import Path

from ai_book_translator.infrastructure.io.read_document.base import ReadDocument
from ai_book_translator.infrastructure.io.read_document.text_reader import TextReader
from ai_book_translator.infrastructure.io.read_document.pdf_reader import PdfReader


def test_read_document_is_abstract():
    # Abstract classes can't be instantiated directly
    with pytest.raises(TypeError):
        ReadDocument()  # type: ignore


def test_from_path_selects_text_reader(tmp_path: Path):
    p = tmp_path / "book.txt"
    p.write_text("Hello world", encoding="utf-8")

    reader = ReadDocument.from_path(p)
    assert isinstance(reader, TextReader)
    assert reader.read(p) == "Hello world"


def test_from_path_selects_pdf_reader(tmp_path: Path):
    # Create a real PDF containing text using reportlab (installed in your environment)
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "book.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 720, "PDF hello")  # 1 inch margin, near top
    c.save()

    reader = ReadDocument.from_path(pdf_path)
    assert isinstance(reader, PdfReader)

    text = reader.read(pdf_path)
    # pypdf extraction sometimes includes extra whitespace/newlines
    assert "PDF hello" in text


def test_from_path_unsupported_extension_raises(tmp_path: Path):
    p = tmp_path / "book.epub"
    p.write_text("fake", encoding="utf-8")

    with pytest.raises(ValueError):
        ReadDocument.from_path(p)
