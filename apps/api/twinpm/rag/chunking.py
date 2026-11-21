"""Heading-aware markdown chunking (~500 tokens, 80-token overlap)."""

from __future__ import annotations

import re
from dataclasses import dataclass

TARGET_TOKENS = 500
OVERLAP_TOKENS = 80
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass(frozen=True)
class Chunk:
    index: int
    heading: str
    content: str
    token_count: int


def approx_tokens(text: str) -> int:
    """Whitespace words * 1.3 approximates BPE tokens closely enough for chunk sizing."""
    return max(1, round(len(text.split()) * 1.3))


def _sections(markdown: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in markdown.splitlines():
        m = _HEADING.match(line)
        if m:
            sections.append((m.group(2).strip(), [line]))
        else:
            sections[-1][1].append(line)
    return [(h, "\n".join(lines).strip()) for h, lines in sections if "\n".join(lines).strip()]


def chunk_markdown(markdown: str) -> list[Chunk]:
    """Pack whole sections up to the target; split oversize sections with word overlap."""
    target_words = int(TARGET_TOKENS / 1.3)
    overlap_words = int(OVERLAP_TOKENS / 1.3)
    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_heading = ""

    def flush() -> None:
        nonlocal buf, buf_heading
        if buf:
            text = "\n\n".join(buf)
            chunks.append(Chunk(len(chunks), buf_heading, text, approx_tokens(text)))
        buf, buf_heading = [], ""

    for heading, text in _sections(markdown):
        words = text.split()
        if len(words) > target_words:
            flush()
            step = target_words - overlap_words
            for start in range(0, len(words), step):
                piece = " ".join(words[start : start + target_words])
                chunks.append(Chunk(len(chunks), heading, piece, approx_tokens(piece)))
                if start + target_words >= len(words):
                    break
            continue
        if sum(len(b.split()) for b in buf) + len(words) > target_words:
            # Carry the tail of the previous chunk forward as overlap.
            tail = " ".join(" ".join(buf).split()[-overlap_words:])
            flush()
            buf = [tail] if tail else []
        if not buf_heading:
            buf_heading = heading
        buf.append(text)
    flush()
    return chunks
