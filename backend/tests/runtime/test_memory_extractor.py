"""Tests for automatic memory extraction."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest

from app.core.agents.memory_extractor import MemoryExtractor
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
            "app.core.agents.memory_engine.vector_store.add_memory",
            lambda content, metadata, memory_id: f"emb_{memory_id}",
        )

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
