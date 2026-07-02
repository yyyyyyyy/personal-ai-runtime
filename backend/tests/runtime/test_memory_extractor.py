"""Tests for automatic memory extraction."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest

from app.core.agents.memory_extractor import MemoryExtractor
from app.core.agents.memory_engine import memory_engine
from app.core.runtime.kernel import Kernel
from app.store.database import Database


async def stub_extract(_text: str) -> list[str]:
    return ["User prefers Python", "User lives in Shanghai"]


@pytest.mark.asyncio
class TestMemoryExtractor:
    async def test_extract_and_store_emits_events(self, tmp_path, monkeypatch):
        db = Database(db_path=str(tmp_path / "extract.db"))
        k = Kernel(db=db)
        monkeypatch.setattr("app.core.agents.memory_engine.kernel", k)
        monkeypatch.setattr(
            "app.store.vector.vector_store.add_memory",
            lambda content, metadata, memory_id: f"emb_{memory_id}",
        )
        monkeypatch.setattr("app.store.vector.vector_store.delete_memory", lambda _id: None)

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
        k = Kernel(db=db)
        monkeypatch.setattr("app.core.agents.memory_engine.kernel", k)
        monkeypatch.setattr(
            "app.store.vector.vector_store.add_memory",
            lambda content, metadata, memory_id: f"emb_{memory_id}",
        )
        monkeypatch.setattr("app.store.vector.vector_store.delete_memory", lambda _id: None)

        # Capture every stored memory so the dedup check on the second pass
        # can see them (the mocked vector index would otherwise be empty).
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
        k = Kernel(db=db)
        monkeypatch.setattr("app.core.agents.memory_engine.kernel", k)
        monkeypatch.setattr(
            "app.store.vector.vector_store.add_memory",
            lambda content, metadata, memory_id: f"emb_{memory_id}",
        )
        monkeypatch.setattr("app.store.vector.vector_store.delete_memory", lambda _id: None)
        # Stub recall to return a high-similarity hit for any query.
        monkeypatch.setattr(
            "app.core.runtime.kernel.kernel_query_state.QueryStateMixin.recall_memory",
            lambda self, query, k=5: [{"id": "m1", "content": "user prefers python", "score": 0.95}],
        )

        async def extract_new(_t: str) -> list[str]:
            return ["User prefers the Python language"]

        extractor = MemoryExtractor(extract_fn=extract_new)
        stored = await extractor.extract_and_store("anything")
        assert stored == [], "high-similarity hit should suppress storage"
