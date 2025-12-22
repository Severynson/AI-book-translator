from __future__ import annotations

from typing import List


def chunk_by_chars(
    text: str,
    chunk_size: int,
    *,
    soft_split: bool = True,
) -> List[str]:
    """
    Split text into chunks of at most `chunk_size` characters.

    soft_split=True (default):
      - Prefer splitting at natural boundaries (paragraphs, newlines, sentence ends, spaces)
      - Fall back to hard splitting only if no good boundary is found

    soft_split=False:
      - Always split exactly by character count
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    if not text:
        return []

    if not soft_split:
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    chunks: List[str] = []
    n = len(text)
    i = 0

    # Try split points in this priority order (first match from the end wins)
    split_seps = ["\n\n", "\n", ". ", "? ", "! ", "; ", ": ", ", ", " "]

    while i < n:
        j = min(i + chunk_size, n)

        # last chunk
        if j >= n:
            tail = text[i:n].strip()
            if tail:
                chunks.append(tail)
            break

        window = text[i:j]
        split_at = None

        for sep in split_seps:
            k = window.rfind(sep)
            if k != -1:
                split_at = i + k + len(sep)
                break

        # Fallback: hard split if no boundary found
        if split_at is None or split_at <= i:
            split_at = j

        chunk = text[i:split_at].strip()
        if chunk:
            chunks.append(chunk)

        i = split_at

    return chunks
