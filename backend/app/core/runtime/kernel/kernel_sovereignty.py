# mypy: disable-error-code="attr-defined"
"""Kernel Sovereignty Mixin — thin ABI wrappers over sovereignty_ops.

Heavy export/import/rebuild logic lives in ``sovereignty_ops`` (not counted
toward God Object LOC).
"""

from __future__ import annotations

from typing import Any

from . import sovereignty_ops as ops

# Re-export for scripts / callers that import from the mixin module.
EXPORT_FORMAT = ops.EXPORT_FORMAT


class SovereigntyMixin:  # type: ignore[attr-defined]
    """Data sovereignty operations — export, import, rebuild."""


    def _drop_event_log_guards(self, conn) -> None:
        return ops._drop_event_log_guards(self, conn)

    def _ensure_event_log_guards(self, conn) -> None:
        return ops._ensure_event_log_guards(self, conn)

    def export_event_log_rows(self, *, conn=None) -> list[dict[str, Any]]:
        """Export full event_log for lossless snapshot (batched seq cursor)."""
        return ops.export_event_log_rows(self, conn=conn)

    def import_event_log_rows(self, rows: list[dict[str, Any]], *, rebuild_projections: bool = True) -> int:
        """Bulk-import events preserving seq/id; optionally rebuild all projections."""
        return ops.import_event_log_rows(self, rows, rebuild_projections=rebuild_projections)

    def table_counts(self, tables: tuple[str, ...]) -> dict[str, int]:
        """Kernel-space row counts for sovereignty verification."""
        return ops.table_counts(self, tables)

    def count_events(self, aggregate_type: str) -> int:
        """Count events in event_log filtered by aggregate_type (kernel-space)."""
        return ops.count_events(self, aggregate_type)

    def bootstrap_chat_from_snapshot(self, conversations: list[dict[str, Any]], messages: list[dict[str, Any]], event_rows: list[dict[str, Any]]) -> dict[str, int]:
        """Emit chat events for legacy snapshots."""
        return ops.bootstrap_chat_from_snapshot(self, conversations, messages, event_rows)

    def export_chat_rows(self, *, conn=None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Export conversation/message projections (denormalized backup)."""
        return ops.export_chat_rows(self, conn=conn)

    def _checkpoint_seq(self, agent_id: str, aggregate_type: str) -> int:
        """Return the last_applied_seq for a per-agent checkpoint (0 if none)."""
        return ops._checkpoint_seq(self, agent_id, aggregate_type)

    def _restore_table_snapshot(self, conn, table: str, rows: list[dict[str, Any]]) -> None:
        return ops._restore_table_snapshot(self, conn, table, rows)

    def save_projection_snapshot(self, aggregate_type: str, agent_id: str = 'kernel') -> dict[str, Any]:
        """Persist projection tables + last_applied_seq for incremental rebuild."""
        return ops.save_projection_snapshot(self, aggregate_type, agent_id)

    def save_projection_snapshots(self, aggregate_types: tuple[str, ...] | list[str] | None = None, agent_id: str = 'kernel') -> list[dict[str, Any]]:
        """Persist checkpoints for one or more aggregates."""
        return ops.save_projection_snapshots(self, aggregate_types, agent_id)

    def rebuild(self, aggregate_type: str, agent_id: str = 'kernel') -> int:
        """Rebuild projection from Event Log (incremental when checkpoint exists)."""
        return ops.rebuild(self, aggregate_type, agent_id)

    def rebuild_all(self) -> dict[str, int]:
        """Rebuild all registered aggregate types."""
        return ops.rebuild_all(self)

    def iter_snapshot_json_chunks(self):
        """Yield UTF-8 chunks of a lossless snapshot JSON document."""
        yield from ops.iter_snapshot_json_chunks(self)

    def snapshot(self) -> dict[str, Any]:
        """Export complete personal snapshot as a dict."""
        return ops.snapshot(self)

    def restore(self, snapshot: dict, read_only: bool = True) -> dict[str, Any]:
        """Import snapshot. Write import requires read_only=False."""
        return ops.restore(self, snapshot, read_only)

    def _restore_from_snapshot(self, snapshot: dict) -> dict:
        """Restore from event_log-based snapshot."""
        return ops._restore_from_snapshot(self, snapshot)

    def _import_legacy_goals_memories(self, snapshot: dict) -> dict[str, Any]:
        """Best-effort import for older lossy snapshots (goals/memories only)."""
        return ops._import_legacy_goals_memories(self, snapshot)

    def erase(self) -> dict:
        """Remove database and vector store files (irreversible)."""
        return ops.erase(self)
