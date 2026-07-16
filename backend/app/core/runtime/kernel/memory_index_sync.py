"""Post-commit memory vector-index sync + durable repair queue.

Extracted from ``kernel.py`` so the God Object LOC budget can shrink without
growing ``runtime_files`` (paired with folding ``projectors.py`` into the
registry). Kernel Space still owns this module.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import TYPE_CHECKING, Any, Protocol

from .constants import MEMORY_INDEX_EVENT_TYPES

if TYPE_CHECKING:
    from .event import Event

logger = logging.getLogger(__name__)

MEMORY_INDEX_RECONCILE_EVENT = "MemoryIndexReconcile"
MEMORY_INDEX_RECONCILE_AGGREGATE = "__full_reconcile__"
# Serializes restore/reconcile, normal post-commit memory sync, and repair
# draining so an old repair cannot overwrite a newly restored vector state.
memory_index_operation_lock = threading.RLock()

# In-process queue of memory events whose Chroma index sync failed.
# Kept as an in-memory mirror of the durable `memory_index_repairs` table for
# cheap runtime observability. The authoritative repair queue lives in
# SQLite and is drained by RuntimeLoop._maintenance; this deque only holds
# the most recent failures (maxlen) so dashboards can surface them without
# hitting the DB.
_MAX_PENDING_MEMORY_INDEX_REPAIRS = 1000
_pending_memory_index_repairs: deque[dict[str, object]] = deque(
    maxlen=_MAX_PENDING_MEMORY_INDEX_REPAIRS
)


def get_pending_memory_index_repairs() -> list[dict[str, object]]:
    """Return a snapshot of memory index events awaiting Chroma reconciliation."""
    return list(_pending_memory_index_repairs)


def clear_pending_memory_index_repairs() -> int:
    """Clear the in-process repair queue; returns number of entries removed.

    NOTE: this only clears the in-memory mirror. The durable rows in
    ``memory_index_repairs`` survive process restarts and are drained by the
    RuntimeLoop repair worker. Tests that need a clean slate should also
    truncate the table.
    """
    count = len(_pending_memory_index_repairs)
    _pending_memory_index_repairs.clear()
    return count


def persist_memory_index_repair(
    db: Any,
    aggregate_id: str,
    event_type: str,
    event_seq: int,
    error: str,
) -> None:
    """Append a failed memory index sync to the durable repair queue.

    Idempotent on (aggregate_id, event_seq): if a row already exists for the
    same event we leave it untouched so the retry counter and status reflect
    the original failure rather than being reset on every emit.
    """
    from datetime import UTC, datetime

    now_iso = datetime.now(UTC).isoformat()
    try:
        with db.get_db() as conn:
            existing = conn.execute(
                "SELECT 1 FROM memory_index_repairs "
                "WHERE aggregate_id = ? AND event_seq = ? LIMIT 1",
                (aggregate_id, event_seq),
            ).fetchone()
            if existing:
                return
            conn.execute(
                "INSERT INTO memory_index_repairs "
                "(aggregate_id, event_type, event_seq, error, status, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (aggregate_id, event_type, event_seq, error[:500], now_iso),
            )
    except Exception:
        # If the table does not exist yet (pre-migration) we cannot persist;
        # fall back to in-memory only so emit_event is not blocked.
        logger.debug(
            "Could not persist memory index repair for %s — table unavailable",
            aggregate_id,
            exc_info=True,
        )


def sync_memory_index(kernel: Any, event: "Event") -> None:
    """Synchronise one event while excluding restore and repair operations."""
    with memory_index_operation_lock:
        _sync_memory_index_locked(kernel, event)


def _sync_memory_index_locked(kernel: Any, event: "Event") -> None:
    """Synchronise memory events with the MemoryIndexPort (if configured).

    Post-commit vector index sync. Called after emit_event has durably
    written the event + projection in a single SQLite transaction.
    Because the event is already durable, a ChromaDB failure here can
    never orphan an event — it only leaves embedding_id NULL until the
    repair queue retries.
    """
    if event.type not in MEMORY_INDEX_EVENT_TYPES:
        return
    content = str(event.payload.get("content", ""))
    try:
        if kernel._memory_index is not None:
            if event.type == "MemoryDeleted":
                kernel._memory_index.delete_memory(event.aggregate_id)
            elif not event.payload.get("embedding_id") and content:
                embedding_id = kernel._memory_index.index_memory(
                    content=content,
                    metadata={
                        "category": str(event.payload.get("category", "general")),
                        "source": str(event.payload.get("source", "")),
                    },
                    memory_id=event.aggregate_id,
                )
                try:
                    kernel.emit_event(
                        "MemoryUpdated", "memory", event.aggregate_id,
                        payload={"embedding_id": embedding_id},
                        actor="kernel",
                    )
                except Exception:
                    logger.debug(
                        "Backfill embedding_id failed for %s",
                        event.aggregate_id,
                        exc_info=True,
                    )
    except Exception as exc:
        # Compensating delete: if index_memory failed partway, attempt to
        # remove any partial ChromaDB state so the repair retry starts clean.
        if event.type != "MemoryDeleted" and kernel._memory_index is not None:
            try:
                kernel._memory_index.delete_memory(event.aggregate_id)
            except Exception:
                logger.debug(
                    "Compensating delete failed for %s",
                    event.aggregate_id,
                    exc_info=True,
                )
        _pending_memory_index_repairs.append({
            "aggregate_id": event.aggregate_id,
            "event_type": event.type,
            "seq": event.seq,
            "error": str(exc),
        })
        persist_memory_index_repair(
            kernel._db, event.aggregate_id, event.type,
            event.seq or 0, str(exc),
        )
        logger.warning(
            "Memory index sync failed for %s (%s) — queued for repair "
            "(in-memory mirror: %d entries). The durable row will be "
            "drained by RuntimeLoop; check 'memory_index_repairs' table "
            "if recovery does not happen.",
            event.aggregate_id, event.type, len(_pending_memory_index_repairs),
            exc_info=True,
        )
    kernel._notify_memory_changed(event, content if content else "")


# ── MemoryIndexPort protocol (relocated from runtime/ports.py) ─────────────


class MemoryIndexPort(Protocol):
    """Semantic memory index for storage and recall.

    The Kernel uses this to synchronise memory events with a vector index
    and to serve ``recall_memory`` / ``recall_knowledge``. If None is
    injected, index sync and recall are no-ops.
    """

    def index_memory(
        self, content: str, metadata: dict | None = None, memory_id: str | None = None
    ) -> str:
        """Index content and return an embedding_id.  Idempotent per memory_id."""
        ...

    def delete_memory(self, memory_id: str) -> None:
        """Remove a memory from the vector index."""
        ...

    def list_memory_ids(self) -> list[str]:
        """Return all memory IDs currently present in the vector index."""
        ...

    def search_memories(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search over derived memories."""
        ...

    def search_memories_batch(
        self, queries: list[str], n_results: int = 5
    ) -> list[list[dict]]:
        """Batch semantic search; return one hit list per query."""
        ...

    def search_knowledge(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search over knowledge chunks."""
        ...
