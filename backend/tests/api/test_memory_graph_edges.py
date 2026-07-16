"""Unit tests for batched memory graph edge building via MemoryIndexPort."""

from app.core.runtime.read_ports.memory import build_memory_graph_edges


def test_build_memory_graph_edges_uses_batch_and_dedupes(monkeypatch):
    calls: list[list[str]] = []

    class FakePort:
        def search_memories_batch(self, queries, n_results=5):
            calls.append(list(queries))
            out = []
            for q in queries:
                if "alpha" in q:
                    out.append([
                        {"id": "m1", "distance": 0.0},
                        {"id": "m2", "distance": 0.2},
                    ])
                else:
                    out.append([
                        {"id": "m2", "distance": 0.0},
                        {"id": "m1", "distance": 0.3},
                    ])
            return out

    class FakeKernel:
        _memory_index = FakePort()

    monkeypatch.setattr(
        "app.core.runtime.read_ports.memory.kernel",
        lambda: FakeKernel(),
    )

    sources = [
        {"id": "m1", "content": "alpha memory about cats"},
        {"id": "m2", "content": "beta memory about dogs"},
    ]
    edges = build_memory_graph_edges(sources)

    assert len(calls) == 1
    assert calls[0] == ["alpha memory about cats", "beta memory about dogs"]
    # Undirected edge deduped to a single m1↔m2
    assert len(edges) == 1
    assert {edges[0]["source"], edges[0]["target"]} == {"m1", "m2"}
    assert edges[0]["weight"] == 0.8  # 1.0 - 0.2 from first hit


def test_build_memory_graph_edges_empty_sources():
    assert build_memory_graph_edges([]) == []


def test_build_memory_graph_edges_no_port_returns_empty(monkeypatch):
    class FakeKernel:
        _memory_index = None

    monkeypatch.setattr(
        "app.core.runtime.read_ports.memory.kernel",
        lambda: FakeKernel(),
    )
    edges = build_memory_graph_edges([{"id": "m1", "content": "x"}])
    assert edges == []
