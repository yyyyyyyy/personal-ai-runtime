"""Tests for unified memory + knowledge retrieval.

recall_unified composes kernel.recall_memory + kernel.recall_knowledge.
Recall goes through Kernel._memory_index (MemoryIndexPort), not the global
vector_store singleton.
"""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime import read_ports
from app.core.runtime.kernel import Kernel
from app.store.database import Database


def make_kernel(tmp_path, memory_index=None):
    db = Database(db_path=str(tmp_path / "unified.db"))
    return Kernel(db=db, memory_index=memory_index), db


def _seed_memory(k: Kernel, mid: str, content: str, source: str = "chat") -> None:
    k.emit_event(
        "MemoryDerived", "memory", mid,
        {"category": "fact", "content": content, "source": source, "confidence": 0.8},
        actor="extractor",
    )


class TestRecallUnified:
    def test_returns_memories_with_source_type(self, tmp_path, monkeypatch):
        class FakeVector:
            def search_memories(self, query, n_results=5):
                return [{"id": "m1", "content": "User prefers dark mode",
                         "metadata": {}, "distance": 0.3}]

            def search_knowledge(self, query, n_results=5):
                return []

        fake = FakeVector()
        k, _ = make_kernel(tmp_path, memory_index=fake)
        _seed_memory(k, "m1", "User prefers dark mode")
        monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

        results = read_ports.recall_unified("dark mode", k_memories=3, k_knowledge=3)

        assert len(results) == 1
        assert results[0]["source_type"] == "memory"
        assert results[0]["provenance"] == "chat"
        assert "dark mode" in results[0]["content"]

    def test_returns_documents_with_source_type(self, tmp_path, monkeypatch):
        class FakeVector:
            def search_memories(self, query, n_results=5):
                return []

            def search_knowledge(self, query, n_results=5):
                return [{
                    "id": "doc1_chunk_0", "content": "Rust ownership rules...",
                    "metadata": {"source_file": "rust.md", "chunk_index": 0},
                    "distance": 0.25,
                }]

        fake = FakeVector()
        k, _ = make_kernel(tmp_path, memory_index=fake)
        monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

        results = read_ports.recall_unified("ownership", k_memories=3, k_knowledge=3)

        assert len(results) == 1
        assert results[0]["source_type"] == "document"
        assert results[0]["provenance"] == "rust.md"

    def test_ranks_by_distance_and_merges(self, tmp_path, monkeypatch):
        class FakeVector:
            def search_memories(self, query, n_results=5):
                return [{"id": "m1", "content": "User likes tea",
                         "metadata": {}, "distance": 0.6}]

            def search_knowledge(self, query, n_results=5):
                return [{
                    "id": "d1", "content": "Tea brewing guide",
                    "metadata": {"source_file": "tea.md"}, "distance": 0.2,
                }]

        fake = FakeVector()
        k, _ = make_kernel(tmp_path, memory_index=fake)
        _seed_memory(k, "m1", "User likes tea")
        monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

        results = read_ports.recall_unified("tea", k_memories=3, k_knowledge=3)

        assert len(results) == 2
        assert results[0]["source_type"] == "document"
        assert results[0]["distance"] == 0.2
        assert results[1]["source_type"] == "memory"
        assert results[1]["distance"] == 0.6

    def test_empty_results_when_nothing_matches(self, tmp_path, monkeypatch):
        class EmptyVector:
            def search_memories(self, query, n_results=5):
                return []

            def search_knowledge(self, query, n_results=5):
                return []

        k, _ = make_kernel(tmp_path, memory_index=EmptyVector())
        monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

        results = read_ports.recall_unified("nothing", k_memories=3, k_knowledge=3)
        assert results == []

    def test_tolerates_vector_store_failure(self, tmp_path, monkeypatch):
        """If one collection throws, the other's results still surface."""

        class FlakeyVector:
            def search_memories(self, query, n_results=5):
                raise RuntimeError("chroma down")

            def search_knowledge(self, query, n_results=5):
                return [{"id": "d1", "content": "fallback doc",
                         "metadata": {"source_file": "f.md"}, "distance": 0.4}]

        k, _ = make_kernel(tmp_path, memory_index=FlakeyVector())
        monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

        results = read_ports.recall_unified("x", k_memories=3, k_knowledge=3)

        assert len(results) == 1
        assert results[0]["source_type"] == "document"
