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
            try:
                _ENCODER = tiktoken.get_encoding("p50k_base")
            except Exception:
                pass
    return _ENCODER  # type: ignore[return-value]


def count_tokens(text: str) -> int:
    """Token count via tiktoken; degrades to char/4 estimate if unavailable."""
    if not text:
        return 0
    enc = _encoder()
    if enc is not None:
        try:
            return len(enc.encode(text, disallowed_special=()))
        except Exception:
            return len(enc.encode(text))
    return max(1, len(text) // 4)


@dataclass
class ChunkConfig:
    target_tokens: int = 500
    overlap_tokens: int = 50
    max_tokens: int = 1500


_CODE_FENCE_START_RE = re.compile(r"^(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^#{1,6}\s")


def chunk_text(text: str, config: ChunkConfig | None = None) -> list[str]:
    """Chunk text into token-bounded, structure-aware pieces with overlap support.

    Strategy:
    1. Break text into atomic structural blocks (sentences, code blocks, headings).
    2. Greedily accumulate atoms into chunks up to target_tokens, accounting for 
       separator overhead.
    3. When a chunk is full, start the next chunk with a tail of atoms from the 
       previous chunk to satisfy overlap_tokens (providing continuity).
    4. Any single atom larger than max_tokens is hard-split by token window, 
       preserving word boundaries where possible.
    """
    cfg = config or ChunkConfig()
    if not text or not text.strip():
        return []

    # 1. Break into atomic blocks (sentences, code blocks, headings)
    atoms = _get_atoms(text)
    
    chunks: list[str] = []
    current_atoms: list[str] = []
    current_tokens = 0
    
    i = 0
    while i < len(atoms):
        atom = atoms[i]
        atom_tokens = count_tokens(atom)
        
        # Handle oversized atom (hard split)
        if atom_tokens > cfg.max_tokens:
            # Flush current if any
            if current_atoms:
                chunks.append("\n\n".join(current_atoms).strip())
                current_atoms = []
                current_tokens = 0
            
            # Hard split the big atom
            remaining = atom
            while count_tokens(remaining) > cfg.target_tokens:
                head, remaining = _hard_token_split(remaining, cfg.target_tokens)
                chunks.append(head.strip())
                # For hard-split overlap, we take tail of head
                if cfg.overlap_tokens > 0:
                    overlap = _get_tail_text(head, cfg.overlap_tokens)
                    remaining = overlap + " " + remaining
            
            if remaining.strip():
                current_atoms = [remaining]
                current_tokens = count_tokens(remaining)
            i += 1
            continue

        # Normal accumulation
        # Add 2 tokens overhead for "\n\n" if not first
        overhead = 2 if current_atoms else 0
        
        if current_tokens + atom_tokens + overhead > cfg.target_tokens and current_atoms:
            # Emit chunk
            chunks.append("\n\n".join(current_atoms).strip())
            
            # Start next chunk with overlap
            if cfg.overlap_tokens > 0:
                # Find how many atoms to keep for overlap
                overlap_buffer: list[str] = []
                overlap_tokens = 0
                for back_atom in reversed(current_atoms):
                    back_tokens = count_tokens(back_atom)
                    if overlap_tokens + back_tokens > cfg.overlap_tokens and overlap_buffer:
                        break
                    overlap_buffer.insert(0, back_atom)
                    overlap_tokens += back_tokens + 2
                
                current_atoms = overlap_buffer
                current_tokens = overlap_tokens
            else:
                current_atoms = []
                current_tokens = 0
        
        current_atoms.append(atom)
        current_tokens += atom_tokens + overhead
        i += 1

    if current_atoms:
        final = "\n\n".join(current_atoms).strip()
        if final:
            chunks.append(final)
            
    return chunks


def _get_atoms(text: str) -> list[str]:
    """Split text into atomic structural blocks (sentences, code blocks, headings)."""
    lines = text.split("\n")
    atoms: list[str] = []
    buffer: list[str] = []
    in_fence = False
    fence_marker = ""

    for line in lines:
        stripped = line.lstrip()
        # Use startswith for speed for common case, then regex for precision
        is_fence = (stripped.startswith("```") or stripped.startswith("~~~")) and \
                   bool(_CODE_FENCE_START_RE.match(stripped))

        if is_fence and not in_fence:
            if buffer:
                atoms.extend(_split_into_sentences("\n".join(buffer)))
                buffer = []
            in_fence = True
            fence_marker = stripped[:3]
            buffer.append(line)
        elif in_fence:
            buffer.append(line)
            if stripped.startswith(fence_marker) and len(stripped) <= len(fence_marker) + 1:
                atoms.append("\n".join(buffer).strip())
                buffer = []
                in_fence = False
        else:
            if _HEADING_RE.match(stripped):
                if buffer:
                    atoms.extend(_split_into_sentences("\n".join(buffer)))
                    buffer = []
                atoms.append(line.strip())
            elif stripped == "":
                if buffer:
                    atoms.extend(_split_into_sentences("\n".join(buffer)))
                    buffer = []
            else:
                buffer.append(line)

    if buffer:
        atoms.extend(_split_into_sentences("\n".join(buffer)))
    
    return [a for a in atoms if a.strip()]


def _split_into_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences."""
    if not text.strip():
        return []
    # Split by sentence boundaries but keep the punctuation
    # This regex looks for punctuation followed by space
    parts = re.split(r"(?<=[。！？.?!\n])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _get_tail_text(text: str, target_tokens: int) -> str:
    """Get approximately the last N tokens of text."""
    enc = _encoder()
    if enc is not None:
        try:
            ids = enc.encode(text, disallowed_special=())
        except Exception:
            ids = enc.encode(text)
        if len(ids) <= target_tokens:
            return text
        tail_ids = ids[-target_tokens:]
        tail = enc.decode(tail_ids)
        # Try to start at a word boundary
        idx = tail.find(" ")
        if idx != -1 and idx < len(tail) // 2:
            return tail[idx:].lstrip()
        return tail
    return text[-(target_tokens * 4):]


def _hard_token_split(text: str, target: int) -> tuple[str, str]:
    """Split text at approximately target tokens, respecting word boundaries."""
    enc = _encoder()
    if enc is not None:
        try:
            ids = enc.encode(text, disallowed_special=())
        except Exception:
            ids = enc.encode(text)
        
        if len(ids) <= target:
            return text, ""
        
        head_ids = ids[:target]
        head = enc.decode(head_ids)
        # Walk back to a whitespace boundary to avoid cutting words
        idx = head.rfind(" ")
        if idx > len(head) // 2:
            head = head[:idx]
        
        tail = text[len(head):].lstrip()
        return head, tail
        
    # Char fallback
    char_target = target * 4
    idx = text.rfind(" ", 0, char_target)
    if idx == -1:
        idx = char_target
    return text[:idx], text[idx:].lstrip()
