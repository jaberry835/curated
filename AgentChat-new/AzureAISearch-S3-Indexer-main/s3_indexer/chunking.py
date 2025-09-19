from __future__ import annotations
from typing import Iterable, List


def chunk_text(text: str, max_len: int = 2000, overlap: int = 500) -> List[str]:
    """Chunk text by characters with overlap. Keeps word boundaries if possible."""
    if not text:
        return []

    max_len = max(1, max_len)
    overlap = max(0, min(overlap, max_len - 1))

    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_len)
        # try to not cut the last word
        slice_ = text[start:end]
        if end < n:
            last_space = slice_.rfind(" ")
            if last_space > max_len * 0.6:  # only if it helps significantly
                slice_ = slice_[:last_space]
                end = start + last_space
        chunks.append(slice_.strip())
        if end >= n:
            break
        start = max(0, end - overlap)
    return [c for c in chunks if c]
