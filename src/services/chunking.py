"""Split extracted pages into overlapping chunks for embedding."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from src.config import settings
from src.services.extraction import ExtractedPage

# Rough characters-per-token ratio for English prose. Good enough for surfacing
# chunk sizes in the API; nothing depends on it being exact.
CHARS_PER_TOKEN = 4

_PAGE_SEPARATOR = "\n\n"
# Preferred break points, best first. A chunk boundary that lands on a paragraph
# break reads far better in a prompt than one that cuts a word in half.
_BREAK_CANDIDATES = ("\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ")


@dataclass(frozen=True)
class TextChunk:
    content: str
    chunk_index: int
    page_number: int | None
    token_estimate: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN) if text else 0


def _flatten(pages: list[ExtractedPage]) -> tuple[str, list[int], list[int]]:
    """Join pages into one string plus a lookup of where each page starts."""
    buffer: list[str] = []
    starts: list[int] = []
    numbers: list[int] = []
    cursor = 0

    for page in pages:
        if not page.text.strip():
            continue
        if buffer:
            buffer.append(_PAGE_SEPARATOR)
            cursor += len(_PAGE_SEPARATOR)
        starts.append(cursor)
        numbers.append(page.number)
        buffer.append(page.text)
        cursor += len(page.text)

    return "".join(buffer), starts, numbers


def _find_break(text: str, start: int, end: int) -> int:
    """Pick the nicest break point in the last third of [start, end)."""
    window_start = start + int((end - start) * 0.66)

    for candidate in _BREAK_CANDIDATES:
        position = text.rfind(candidate, window_start, end)
        if position != -1:
            return position + len(candidate)

    return end


def chunk_pages(
    pages: list[ExtractedPage],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[TextChunk]:
    """Chunk pages into overlapping windows, tagging each with its start page."""
    chunk_size = chunk_size if chunk_size is not None else settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.CHUNK_OVERLAP

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")

    text, page_starts, page_numbers = _flatten(pages)
    if not text.strip():
        return []

    chunks: list[TextChunk] = []
    position = 0
    length = len(text)

    while position < length:
        end = min(position + chunk_size, length)
        if end < length:
            end = _find_break(text, position, end)

        content = text[position:end].strip()
        if content:
            page_index = max(0, bisect_right(page_starts, position) - 1)
            chunks.append(
                TextChunk(
                    content=content,
                    chunk_index=len(chunks),
                    page_number=page_numbers[page_index] if page_numbers else None,
                    token_estimate=estimate_tokens(content),
                )
            )

        if end >= length:
            break

        # Step forward by at least one character so an unbreakable run of text
        # can never spin this loop forever.
        position = max(end - chunk_overlap, position + 1)

    return chunks


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[TextChunk]:
    return chunk_pages([ExtractedPage(number=1, text=text)], chunk_size, chunk_overlap)
