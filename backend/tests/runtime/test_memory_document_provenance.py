"""Tests for Memory ↔ Knowledge provenance (Phase 1.5).

Verifies that MemoryDerived events carrying source_document_id / name are
projected into the memories table and surfaced through query_state, so the
frontend can render "derived from: <doc>" and link back to the document.
"""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database


def make_kernel(tmp_path):
    return Kernel(db=Database(db_path=str(tmp_path / "prov.db")))


class TestMemoryDocumentProvenance:
    def test_provenance_fields_projected(self, tmp_path):
        k = make_kernel(tmp_path)
        k.emit_event(
            "MemoryDerived", "memory", "m1",
            {
                "category": "fact",
                "content": "Rust ownership prevents data races at compile time",
                "source": "chat",
                "confidence": 0.8,
                "source_document_id": "doc-abc",
                "source_document_name": "rust-book.pdf",
            },
            actor="extractor",
        )

        rows = k.query_state("memories", id="m1")
        assert len(rows) == 1
        row = rows[0]
        assert row["source_document_id"] == "doc-abc"
        assert row["source_document_name"] == "rust-book.pdf"

    def test_provenance_optional_when_absent(self, tmp_path):
        """Memories not derived from a document have NULL provenance fields."""
        k = make_kernel(tmp_path)
        k.emit_event(
            "MemoryDerived", "memory", "m2",
            {"category": "fact", "content": "User likes coffee", "confidence": 0.7},
            actor="extractor",
        )

        rows = k.query_state("memories", id="m2")
        assert len(rows) == 1
        row = rows[0]
        assert row["source_document_id"] is None
        assert row["source_document_name"] is None

    def test_provenance_survives_rebuild(self, tmp_path):
        """Rebuilding memories from event_log preserves provenance."""
        k = make_kernel(tmp_path)
        k.emit_event(
            "MemoryDerived", "memory", "m3",
            {
                "category": "fact",
                "content": "Q4 revenue grew 20% YoY",
                "confidence": 0.9,
                "source_document_id": "doc-fin",
                "source_document_name": "annual-report.pdf",
            },
            actor="extractor",
        )

        k.rebuild("memory")

        rows = k.query_state("memories", id="m3")
        assert len(rows) == 1
        assert rows[0]["source_document_id"] == "doc-fin"
        assert rows[0]["source_document_name"] == "annual-report.pdf"
