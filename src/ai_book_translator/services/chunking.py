from __future__ import annotations
from typing import List

def chunk_by_chars(text: str, chunk_size: int) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    text = text or ""
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
