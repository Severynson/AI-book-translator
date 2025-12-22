from ai_book_translator.services.chunking import chunk_by_chars

def test_chunk_by_chars():
    assert chunk_by_chars("abcdef", 2) == ["ab", "cd", "ef"]
