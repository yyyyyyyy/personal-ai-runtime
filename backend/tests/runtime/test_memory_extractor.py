"""Tests for automatic memory extraction."""

import pytest

from app.core.agents.memory_engine import memory_engine
from app.core.agents.memory_extractor import MemoryExtractor
from app.core.runtime.kernel import Kernel
from app.store.database import Database


async def stub_extract(_text: str) -> list[str]:
    return ["User prefers Python", "User lives in Shanghai"]


@pytest.mark.asyncio
class TestMemoryExtractor:
    async def test_extract_and_store_emits_events(self, tmp_path, monkeypatch):
        db = Database(db_path=str(tmp_path / "extract.db"))
        # No memory_index → index sync is a no-op (avoid Chroma in unit tests).
        k = Kernel(db=db, memory_index=None)
        monkeypatch.setattr("app.core.agents.memory_engine.kernel", k)
        monkeypatch.setattr(memory_engine, "search_relevant_memories", lambda *_a, **_k: [])

        extractor = MemoryExtractor(extract_fn=stub_extract)
        stored = await extractor.extract_and_store("User said they like Python")
        assert len(stored) == 2

        with db.get_db() as conn:
            rows = conn.execute("SELECT * FROM memories").fetchall()
        assert len(rows) == 2
        assert all(r["source"] == "conversation" for r in rows)

    async def test_empty_conversation_noop(self, tmp_path, monkeypatch):
        db = Database(db_path=str(tmp_path / "extract2.db"))
        k = Kernel(db=db)
        monkeypatch.setattr("app.core.agents.memory_engine.kernel", k)

        extractor = MemoryExtractor(extract_fn=stub_extract)
        stored = await extractor.extract_and_store("   ")
        assert stored == []

    async def test_duplicate_fact_not_stored_again(self, tmp_path, monkeypatch):
        """When the same fact is extracted twice, the second pass is deduped."""
        db = Database(db_path=str(tmp_path / "extract_dedup.db"))
        k = Kernel(db=db, memory_index=None)
        monkeypatch.setattr("app.core.agents.memory_engine.kernel", k)

        stored_contents: list[str] = []

        def _fake_search(query: str, n_results: int = 5) -> list[dict]:
            # Return previously stored contents as recall hits.
            return [{"id": f"m{i}", "content": c} for i, c in enumerate(stored_contents)]

        monkeypatch.setattr(memory_engine, "search_relevant_memories", _fake_search)

        original_store = memory_engine.store_memory

        def _capturing_store(content, *args, **kwargs):
            stored_contents.append(content)
            return original_store(content, *args, **kwargs)

        monkeypatch.setattr(memory_engine, "store_memory", _capturing_store)

        extractor = MemoryExtractor(extract_fn=stub_extract)
        first = await extractor.extract_and_store("User said they like Python")
        assert len(first) == 2

        # Second extraction of the SAME facts should be deduped (lexical match
        # against the memories just stored, surfaced via the search stub).
        second = await extractor.extract_and_store("User said they like Python")
        assert second == [], "duplicate facts must not be stored again"

        with db.get_db() as conn:
            rows = conn.execute("SELECT * FROM memories").fetchall()
        assert len(rows) == 2, "no new rows should have been added"

    async def test_high_similarity_score_dedup(self, tmp_path, monkeypatch):
        """A recall hit with similarity >= threshold dedupes even non-identical text."""
        db = Database(db_path=str(tmp_path / "extract_sim.db"))

        class FakeIndex:
            def search_memories(self, query, n_results=5):
                return [
                    {
                        "id": "m1",
                        "content": "user prefers python",
                        "score": 0.95,
                        "distance": 0.05,
                    }
                ]

            def search_knowledge(self, query, n_results=5):
                return []

            def index_memory(self, content, metadata=None, memory_id=None):
                return f"emb_{memory_id}"

            def delete_memory(self, memory_id):
                return None

            def list_memory_ids(self):
                return []

        k = Kernel(db=db, memory_index=FakeIndex())
        monkeypatch.setattr("app.core.agents.memory_engine.kernel", k)

        async def extract_new(_t: str) -> list[str]:
            return ["User prefers the Python language"]

        extractor = MemoryExtractor(extract_fn=extract_new)
        stored = await extractor.extract_and_store("anything")
        assert stored == [], "high-similarity hit should suppress storage"

    async def test_schedule_holds_strong_task_reference(self):
        """schedule() must retain the task so CPython does not GC it."""
        extractor = MemoryExtractor(extract_fn=stub_extract)
        scheduled = extractor.schedule("User likes Rust", source="test")
        assert scheduled is True
        assert isinstance(extractor._pending_tasks, set)

    async def test_schedule_dedupes_same_key(self):
        extractor = MemoryExtractor(extract_fn=stub_extract)
        assert extractor.schedule("same text", dedup_key="turn-1") is True
        assert extractor.schedule("same text", dedup_key="turn-1") is False

    async def test_schedule_drops_when_backlog_full(self, monkeypatch):
        extractor = MemoryExtractor(extract_fn=stub_extract)

        class _Forever:
            def done(self):
                return False

        # Saturate the pending set with unfinished stubs.
        extractor._pending_tasks = {_Forever(), _Forever(), _Forever()}  # type: ignore[arg-type]
        assert extractor.schedule("overflow", dedup_key="overflow-1") is False

    async def test_cloud_extract_failure_is_logged(self, monkeypatch):
        """Cloud extraction failures must surface as a warning, not silent []."""
        from unittest.mock import patch

        from app.core.agents import memory_extractor as me_mod

        class _BoomClient:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**_kw):
                        raise RuntimeError("simulated auth failure")

        class _BoomProvider:
            name = "boom"
            model = "boom-model"

        from app.core.agents import llm_failover
        monkeypatch.setattr(
            llm_failover.llm_router,
            "get_client",
            lambda: (_BoomClient(), _BoomProvider()),
        )
        monkeypatch.setattr(
            "app.core.agents.brain_telemetry.record_llm_outcome",
            lambda **_kwargs: None,
        )

        extractor = me_mod.MemoryExtractor()
        with patch.object(me_mod.logger, "warning") as mock_warn:
            result = await extractor._cloud_extract("some text")
        assert result == []
        assert mock_warn.called, "failure must be logged at WARNING level"
        assert any(
            "Cloud memory extraction failed" in str(call)
            for call in mock_warn.call_args_list
        )
