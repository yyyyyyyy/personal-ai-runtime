"""T4 acceptance test: Memory as derived decaying belief with rebuild support."""

class TestMemoryBelief:
    def test_memory_derived_and_rebuild(self, isolated_kernel):
        k, _db = isolated_kernel
        k.emit_event("MemoryDerived", "memory", "m1", {
            "category": "preference", "content": "User prefers Rust", "confidence": 0.8,
        }, actor="extractor")
        k.emit_event("MemoryDerived", "memory", "m2", {
            "category": "fact", "content": "User lives in Beijing", "confidence": 0.9,
        }, actor="extractor")

        # Rebuild and verify
        k.rebuild("memory")
        with k._db.get_db() as conn:
            rows = conn.execute("SELECT * FROM memories ORDER BY created_at").fetchall()
        assert len(rows) == 2
        by_id = {r["id"]: dict(r) for r in rows}
        assert by_id["m1"]["confidence"] == 0.8
        assert by_id["m2"]["content"] == "User lives in Beijing"

    def test_memory_decayed_lowers_confidence(self, isolated_kernel):
        k, _db = isolated_kernel
        k.emit_event("MemoryDerived", "memory", "m1", {
            "category": "preference", "content": "User likes coffee", "confidence": 0.7,
        }, actor="extractor")
        k.emit_event("MemoryDecayed", "memory", "m1", {"confidence": 0.2}, actor="scheduler")

        with k._db.get_db() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?", ("m1",)).fetchone()
        assert dict(row)["confidence"] == 0.2
        assert dict(row)["decayed_at"] is not None

    def test_memory_revoked_zeroes_confidence(self, isolated_kernel):
        k, _db = isolated_kernel
        k.emit_event("MemoryDerived", "memory", "m1", {
            "category": "fact", "content": "User works at Company X", "confidence": 0.6,
        }, actor="extractor")
        k.emit_event("MemoryRevoked", "memory", "m1", {}, actor="extractor")

        with k._db.get_db() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?", ("m1",)).fetchone()
        assert dict(row)["confidence"] == 0.0

    def test_rebuild_memory_projection(self, isolated_kernel):
        k, _db = isolated_kernel
        k.emit_event("MemoryDerived", "memory", "m1", {
            "category": "preference", "content": "Rust", "confidence": 0.8,
        }, actor="extractor")
        k.emit_event("MemoryDerived", "memory", "m2", {
            "category": "fact", "content": "Beijing", "confidence": 0.9,
        }, actor="extractor")
        k.emit_event("MemoryDecayed", "memory", "m1", {"confidence": 0.3}, actor="scheduler")

        before = []
        with k._db.get_db() as conn:
            before = [dict(r) for r in conn.execute("SELECT * FROM memories ORDER BY created_at").fetchall()]

        k.rebuild("memory")

        after = []
        with k._db.get_db() as conn:
            after = [dict(r) for r in conn.execute("SELECT * FROM memories ORDER BY created_at").fetchall()]

        assert before == after, "memory projection must be byte-identical after rebuild"
        assert len(after) == 2

    def test_memory_event_persists_when_chroma_fails(self, isolated_kernel):
        k, _db = isolated_kernel
        class BrokenVectorStore:
            def delete_memory(self, *_args, **_kwargs):
                raise RuntimeError("chroma unavailable")

            def index_memory(self, *_args, **_kwargs):
                raise RuntimeError("chroma unavailable")

        k._memory_index = BrokenVectorStore()

        k.emit_event(
            "MemoryDerived",
            "memory",
            "m-chroma-fail",
            {"category": "fact", "content": "Survives Chroma outage", "confidence": 0.5},
            actor="test",
        )

        rows = k.query_state("memories", id="m-chroma-fail")
        assert len(rows) == 1
        assert rows[0]["content"] == "Survives Chroma outage"

        from app.core.runtime.kernel.kernel import (
            clear_pending_memory_index_repairs,
            get_pending_memory_index_repairs,
        )

        pending = get_pending_memory_index_repairs()
        assert any(p.get("aggregate_id") == "m-chroma-fail" for p in pending)
        assert clear_pending_memory_index_repairs() >= 1
        assert get_pending_memory_index_repairs() == []
