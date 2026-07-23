"""Durable resume registry for plan steps paused on approval.

When Execute/Background hits ``pending``, the approval_id is mapped to the
remaining plan so ``ApproveRequested`` can re-dispatch after the approved
tool runs.

Lives outside ``handlers/`` so expiry / governance can clear entries without
importing the handler package (side-effect ``@subscribe`` registration).

**Durability:** rows live in APP_STORAGE ``plan_resumes`` (SQLite), keyed by
``approval_id``. A process restart keeps pending resumes; clearing happens on
take / deny / auto-expire. This is operational continuation state — not a
governed fact (the approval row remains the governance authority).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal

ResumeKind = Literal["execute", "background"]

logger = logging.getLogger(__name__)

# Test override — production resolves via ``app.store.database.db``.
_db_override: Any | None = None


@dataclass(frozen=True)
class PlanResume:
    kind: ResumeKind
    resume_from: int
    previous_output: dict[str, Any] | None = None
    action_id: str = ""
    task_id: str = ""
    plan_json: str = ""

    def with_step_output(self, step_index: int, result: str, *, limit: int = 1000) -> PlanResume:
        """Return a copy with ``step_{n}_output`` set (Approve → resume handoff)."""
        prev = dict(self.previous_output or {})
        if step_index >= 0:
            prev[f"step_{step_index}_output"] = result[:limit]
        return replace(self, previous_output=prev)

    def to_row(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "resume_from": int(self.resume_from),
            "previous_output_json": json.dumps(
                self.previous_output or {}, ensure_ascii=False
            ),
            "action_id": self.action_id or "",
            "task_id": self.task_id or "",
            "plan_json": self.plan_json or "",
        }

    @classmethod
    def from_row(cls, row: Any) -> PlanResume:
        raw = row["previous_output_json"]
        try:
            prev = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            prev = {}
        if not isinstance(prev, dict):
            prev = {}
        return cls(
            kind=row["kind"],  # type: ignore[arg-type]
            resume_from=int(row["resume_from"]),
            previous_output=prev or None,
            action_id=row["action_id"] or "",
            task_id=row["task_id"] or "",
            plan_json=row["plan_json"] or "",
        )


def configure_plan_resume_db(db: Any | None) -> None:
    """Bind the Database used for plan resumes (tests / explicit Kernel db)."""
    global _db_override
    _db_override = db


def _resolve_db(db: Any | None = None) -> Any:
    if db is not None:
        return db
    if _db_override is not None:
        return _db_override
    from app.store.database import db as global_db

    return global_db


def _db_from_kernel(kernel: Any | None) -> Any | None:
    """Prefer Kernel's Database when it is a real store instance."""
    if kernel is None:
        return None
    candidate = getattr(kernel, "_db", None)
    # Avoid MagicMock auto-attrs in unit tests.
    cls_name = type(candidate).__name__
    if candidate is None or cls_name == "MagicMock":
        return None
    return candidate


def register_plan_resume(
    approval_id: str,
    resume: PlanResume,
    *,
    db: Any | None = None,
    kernel: Any | None = None,
) -> None:
    if not approval_id:
        return
    database = _resolve_db(db if db is not None else _db_from_kernel(kernel))
    row = resume.to_row()
    now = datetime.now(UTC).isoformat()
    with database.get_db() as conn:
        conn.execute(
            """INSERT INTO plan_resumes
               (approval_id, kind, resume_from, previous_output_json,
                action_id, task_id, plan_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(approval_id) DO UPDATE SET
                 kind = excluded.kind,
                 resume_from = excluded.resume_from,
                 previous_output_json = excluded.previous_output_json,
                 action_id = excluded.action_id,
                 task_id = excluded.task_id,
                 plan_json = excluded.plan_json,
                 created_at = excluded.created_at""",
            (
                approval_id,
                row["kind"],
                row["resume_from"],
                row["previous_output_json"],
                row["action_id"],
                row["task_id"],
                row["plan_json"],
                now,
            ),
        )


def peek_plan_resume(
    approval_id: str,
    *,
    db: Any | None = None,
    kernel: Any | None = None,
) -> PlanResume | None:
    if not approval_id:
        return None
    database = _resolve_db(db if db is not None else _db_from_kernel(kernel))
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM plan_resumes WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
    if row is None:
        return None
    return PlanResume.from_row(row)


def take_plan_resume(
    approval_id: str,
    *,
    db: Any | None = None,
    kernel: Any | None = None,
) -> PlanResume | None:
    if not approval_id:
        return None
    database = _resolve_db(db if db is not None else _db_from_kernel(kernel))
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM plan_resumes WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "DELETE FROM plan_resumes WHERE approval_id = ?",
            (approval_id,),
        )
    return PlanResume.from_row(row)


def clear_plan_resumes_for_background_task(
    task_id: str,
    *,
    db: Any | None = None,
    kernel: Any | None = None,
) -> int:
    """Drop durable resumes for a background task (cancel / cleanup)."""
    if not task_id:
        return 0
    database = _resolve_db(db if db is not None else _db_from_kernel(kernel))
    with database.get_db() as conn:
        cur = conn.execute(
            "DELETE FROM plan_resumes WHERE kind = ? AND task_id = ?",
            ("background", task_id),
        )
        return int(cur.rowcount or 0)


def clear_plan_resumes(*, db: Any | None = None) -> None:
    """Delete all resume rows (test helper)."""
    database = _resolve_db(db)
    with database.get_db() as conn:
        conn.execute("DELETE FROM plan_resumes")
