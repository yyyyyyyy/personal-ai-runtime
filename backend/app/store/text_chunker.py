"""Semantic text chunking for knowledge documents.

Token-based chunking with overlap, plus structure-aware splitting for Markdown:
- Code fences (```...```) are never split mid-block.
- Markdown headings start new chunks.
- Long paragraphs are split by sentence boundaries when they exceed the limit.

Plain text (txt/csv/json) falls back to token-window chunking.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import tiktoken

logger = logging.getLogger(__name__)

# Reuse a single encoding across calls. cl100k is the encoding used by
# gpt-4o / text-embedding models; for chunking purposes any BPE encoding is
# a good enough proxy for "token budget".
_ENCODER: tiktoken.Encoding | None = None


def _encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        try:
            _ENCODER = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback: p50k (text-davinci). If that fails too, we degrade
            # gracefully to character-based estimates.
            try:
                _ENCODER = tiktoken.get_encoding("p50k_base")
            except Exception:
                _ENCODER = None  # type: ignore[assignment]
    return _ENCODER  # type: ignore[return-value]


def count_tokens(text: str) -> int:
    """Token count via tiktoken; degrades to char/4 estimate if unavailable."""
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // 4)


@dataclass
class ChunkConfig:
    target_tokens: int = 500
    overlap_tokens: int = 50
    max_tokens: int = 1500


_CODE_FENCE_RE = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)
_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)


def chunk_text(text: str, config: ChunkConfig | None = None) -> list[str]:
    """Chunk text into token-bounded, structure-aware pieces.

    Strategy:
    1. Split into structural blocks (code fences kept whole; markdown headings
       and blank-line-separated paragraphs form block boundaries).
    2. Greedily accumulate blocks into chunks up to target_tokens.
    3. When a chunk is full, start the next chunk with the last overlap_tokens
       worth of text from the previous chunk for continuity.
    4. Any single block larger than max_tokens is hard-split by sentences.
    """
    cfg = config or ChunkConfig()
    if not text or not text.strip():
        return []

    blocks = _split_structural_blocks(text)
    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    def _flush() -> None:
        nonlocal current_parts, current_tokens
        if current_parts:
            chunk = "\n\n".join(current_parts).strip()
            if chunk:
                chunks.append(chunk)
            current_parts = []
            current_tokens = 0

    for block in blocks:
        block_tokens = count_tokens(block)

        # Hard-split oversized blocks by sentence.
        if block_tokens > cfg.max_tokens:
            _flush()
            for piece in _split_oversized(block, cfg):
                chunks.append(piece)
            continue

        # If this single block already exceeds the target, emit it as its own
        # chunk (or sentence-split it) rather than silently accumulating.
        if block_tokens > cfg.target_tokens:
            if current_parts:
                _flush()
            for piece in _split_oversized(block, cfg):
                chunks.append(piece)
            continue

        if current_tokens + block_tokens > cfg.target_tokens and current_parts:
            _flush()
            current_parts = []
            current_tokens = 0

        current_parts.append(block)
        current_tokens += block_tokens

    _flush()
    return chunks


def _split_structural_blocks(text: str) -> list[str]:
    """Split text into blocks, keeping code fences intact."""
    lines = text.split("\n")
    blocks: list[str] = []
    buffer: list[str] = []
    in_fence = False
    fence_marker = ""

    for line in lines:
        stripped = line.lstrip()
        is_fence = bool(re.match(r"^(`{3,}|~{3,})", stripped))

        if is_fence and not in_fence:
            # Flush paragraph buffer before starting a code block
            if buffer:
                _emit_block(blocks, buffer)
                buffer = []
            in_fence = True
            fence_marker = stripped[:3]
            buffer.append(line)
        elif in_fence:
            buffer.append(line)
            # Closing fence matches the opening marker
            if stripped.startswith(fence_marker) and len(stripped) <= len(fence_marker) + 1:
                _emit_block(blocks, buffer)
                buffer = []
                in_fence = False
                fence_marker = ""
        else:
            buffer.append(line)
            # Blank line or heading ends a paragraph block
            if stripped == "" or _HEADING_RE.match(stripped):
                _emit_block(blocks, buffer)
                buffer = []

    if buffer:
        _emit_block(blocks, buffer)
    return [b for b in blocks if b.strip()]


def _emit_block(blocks: list[str], buffer: list[str]) -> None:
    text = "\n".join(buffer).strip()
    if text:
        blocks.append(text)


def _split_oversized(block: str, cfg: ChunkConfig) -> list[str]:
    """Split a block larger than max_tokens by sentences, then by tokens."""
    # Prefer sentence boundaries for readability.
    sentences = re.split(r"(?<=[。！？.?!\n])\s+", block)
    pieces: list[str] = []
    current = ""
    current_t = 0

    for sent in sentences:
        st = count_tokens(sent)
        if current_t + st > cfg.target_tokens and current:
            pieces.append(current.strip())
            current = ""
            current_t = 0
        current += sent
        current_t += st

        # If a single sentence exceeds max_tokens, hard-split by token window.
        while current_t > cfg.max_tokens:
            hard = _hard_token_split(current, cfg.target_tokens)
            if hard:
                pieces.append(hard[0].strip())
                current = hard[1]
                current_t = count_tokens(current)
            else:
                break

    if current.strip():
        pieces.append(current.strip())
    return pieces


def _hard_token_split(text: str, target: int) -> tuple[str, str]:
    """Split text at approximately target tokens, respecting word boundaries."""
    enc = _encoder()
    if enc is not None:
        ids = enc.encode(text)
        if len(ids) <= target:
            return text, ""
        # Decode the first target tokens, trim back to last space for safety.
        head_ids = ids[:target]
        head = enc.decode(head_ids)
        # Walk back to a whitespace boundary
        idx = head.rfind(" ")
        if idx > target // 2:
            head = head[:idx]
        tail = text[len(head):]
        return head, tail.lstrip()
    # Char fallback
    char_target = target * 4
    idx = text.rfind(" ", 0, char_target)
    if idx == -1:
        idx = char_target
    return text[:idx], text[idx:].lstrip()
