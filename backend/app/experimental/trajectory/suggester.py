"""Propose TrajectoryLinked edges from conversation / memory text (proposed only)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.experimental.trajectory.engine import link_event, load_merged_registry
from app.experimental.trajectory.registry import load_yaml_registry

logger = logging.getLogger(__name__)

# Keyword hints per trajectory id (extends registry descriptions).
_TRAJECTORY_KEYWORDS: dict[str, list[str]] = {
    "career-entrepreneurship-2026": ["创业", "辞职", "离职", "跳槽", "单干", "startup"],
    "career-corporate-stability-2026": ["稳定", "留下", "暂缓", "继续工作", "不辞职"],
}


def _keywords_for(trajectory_id: str, entry: dict[str, Any]) -> list[str]:
    base = list(_TRAJECTORY_KEYWORDS.get(trajectory_id, []))
    desc = entry.get("description") or ""
    if "entrepreneurship" in trajectory_id or "创业" in desc:
        base.extend(["创业", "辞职"])
    return list(dict.fromkeys(base))


def match_trajectory_ids(text: str, registry: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Return trajectory ids whose keywords appear in text."""
    registry = registry or load_yaml_registry()
    text_lower = text.lower()
    matched: list[str] = []

    def _text_has(kw: str) -> bool:
        return kw.lower() in text_lower or kw in text

    for tid, entry in registry.items():
        if entry.get("status", "active") != "active":
            continue
        for kw in _keywords_for(tid, entry):
            if _text_has(kw):
                matched.append(tid)
                break

    # Fallback when registry yaml absent (e.g. isolated test db)
    for tid, kws in _TRAJECTORY_KEYWORDS.items():
        if tid in matched:
            continue
        if any(_text_has(kw) for kw in kws):
            matched.append(tid)

    return matched


def load_merged_registry_from_kernel() -> dict[str, dict[str, Any]]:
    from app.core.runtime import kernel_instance
    from app.experimental.trajectory.engine import load_merged_registry

    return load_merged_registry(kernel_instance.kernel)


def _latest_memory_event_seq(kernel, memory_id: str) -> int | None:
    events = kernel.read_events(
        aggregate_type="memory",
        aggregate_id=memory_id,
        order="desc",
        limit=5,
    )
    for event in events:
        if event.type == "MemoryDerived" and event.seq is not None:
            return event.seq
    return None


def _existing_link(kernel, trajectory_id: str, event_seq: int) -> bool:
    data = kernel.query_trajectory(trajectory_id)
    if not data:
        return False
    return any(lnk.get("event_seq") == event_seq for lnk in data.get("links", []))


def propose_links_for_memory(
    kernel,
    memory_id: str,
    content: str,
    *,
    rationale: str | None = None,
) -> list[str]:
    """Create proposed TrajectoryLinked edges for a memory event. Returns link ids."""
    event_seq = _latest_memory_event_seq(kernel, memory_id)
    if event_seq is None:
        return []

    registry = load_merged_registry(kernel) or load_yaml_registry()
    created: list[str] = []
    for tid in match_trajectory_ids(content, registry):
        if _existing_link(kernel, tid, event_seq):
            continue
        ev = link_event(
            kernel,
            tid,
            event_seq,
            actor="system",
            confidence=0.55,
            rationale=rationale or f"keyword match: {content[:80]}",
            claim_status="proposed",
        )
        link_id = (ev.payload or {}).get("link_id")
        if link_id:
            created.append(link_id)
    return created


def propose_links_for_text(kernel, text: str, event_seq: int, **kwargs) -> list[str]:
    """Link arbitrary event seq (e.g. ConversationRecorded) to trajectories."""
    registry = load_merged_registry(kernel) or load_yaml_registry()
    created: list[str] = []
    for tid in match_trajectory_ids(text, registry):
        if _existing_link(kernel, tid, event_seq):
            continue
        ev = link_event(
            kernel,
            tid,
            event_seq,
            actor="system",
            confidence=0.5,
            rationale=kwargs.get("rationale"),
            claim_status="proposed",
        )
        link_id = (ev.payload or {}).get("link_id")
        if link_id:
            created.append(link_id)
    return created


class TrajectorySuggester:
    """Fire-and-forget trajectory link proposals after memory extraction."""

    def after_memory_stored(self, memory_id: str, content: str, source: str = "") -> None:
        from app.core.runtime import kernel_instance

        try:
            propose_links_for_memory(
                kernel_instance.kernel,
                memory_id,
                content,
                rationale=f"auto-suggest from {source}" if source else None,
            )
        except Exception:
            logger.exception("Trajectory link proposal failed for memory %s", memory_id)

    def schedule_after_memory(self, memory_id: str, content: str, source: str = "") -> None:
        async def _run() -> None:
            self.after_memory_stored(memory_id, content, source)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run())
        except RuntimeError:
            pass

    def after_conversation_recorded(
        self, event_seq: int, text: str, source: str = ""
    ) -> None:
        from app.core.runtime import kernel_instance

        try:
            propose_links_for_text(
                kernel_instance.kernel,
                text,
                event_seq,
                rationale=f"auto-suggest from conversation {source}" if source else None,
            )
        except Exception:
            logger.exception("Trajectory link proposal failed for conversation seq %s", event_seq)

    def schedule_after_conversation(self, event_seq: int, text: str, source: str = "") -> None:
        async def _run() -> None:
            self.after_conversation_recorded(event_seq, text, source)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run())
        except RuntimeError:
            self.after_conversation_recorded(event_seq, text, source)


trajectory_suggester = TrajectorySuggester()
