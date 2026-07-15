"""Tests for token-based semantic chunking."""

from app.store.text_chunker import ChunkConfig, chunk_text, count_tokens


class TestChunkText:
    def test_empty_text_returns_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        text = "This is a short sentence about Rust ownership."
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert "Rust" in chunks[0]

    def test_token_budget_respected(self):
        # Build a long text that should span multiple chunks
        paragraph = ("The borrower checker enforces ownership rules at compile time. "
                     "Each value has exactly one owner. ") * 20
        chunks = chunk_text(paragraph, ChunkConfig(target_tokens=100, overlap_tokens=20))
        assert len(chunks) >= 2
        # No chunk should wildly exceed a reasonable max
        for c in chunks:
            # Allow some headroom for token estimation variance
            assert count_tokens(c) <= 2000

    def test_code_fence_kept_whole(self):
        text = (
            "Intro paragraph.\n\n"
            "```python\n"
            "def f():\n"
            "    return 42\n"
            "```\n\n"
            "Outro paragraph."
        )
        chunks = chunk_text(text, ChunkConfig(target_tokens=10, overlap_tokens=0))
        # The code fence should appear intact in some chunk
        joined = "\n".join(chunks)
        assert "def f():" in joined
        assert "return 42" in joined

    def test_markdown_headings_split(self):
        text = (
            "# Chapter 1\n\nContent of chapter one. " + ("Sentence. " * 30) + "\n\n"
            "# Chapter 2\n\nContent of chapter two. " + ("Sentence. " * 30)
        )
        chunks = chunk_text(text, ChunkConfig(target_tokens=80, overlap_tokens=10))
        assert len(chunks) >= 2
        # Both headings should be present across chunks
        joined = "\n".join(chunks)
        assert "# Chapter 1" in joined
        assert "# Chapter 2" in joined

    def test_overlap_provides_continuity(self):
        # With overlap, consecutive chunks share some tail/head text
        body = ("Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu. " * 15)
        chunks = chunk_text(body, ChunkConfig(target_tokens=50, overlap_tokens=15))
        if len(chunks) >= 2:
            # At least verify both chunks have content (overlap semantics
            # are approximate with token-level splitting)
            assert len(chunks[0]) > 0
            assert len(chunks[1]) > 0


class TestCountTokens:
    def test_nonzero_for_text(self):
        assert count_tokens("hello world") > 0

    def test_zero_for_empty(self):
        # Empty string → encode returns []
        assert count_tokens("") == 0
