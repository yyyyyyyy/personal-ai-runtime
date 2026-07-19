"""In-process resume registry for plan steps paused on approval.

When Execute/Background hits ``pending``, the approval_id is mapped to the
remaining plan so ``ApproveRequested`` can re-dispatch after the approved
tool runs.

Lives outside ``handlers/`` so expiry / governance can clear entries without
importing the handler package (side-effect ``@subscribe`` registration).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from typing import Any, Literal

ResumeKind = Literal["execute", "background"]


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


_lock = threading.Lock()
_resumes: dict[str, PlanResume] = {}


def register_plan_resume(approval_id: str, resume: PlanResume) -> None:
    if not approval_id:
        return
    with _lock:
        _resumes[approval_id] = resume


def take_plan_resume(approval_id: str) -> PlanResume | None:
    if not approval_id:
        return None
    with _lock:
        return _resumes.pop(approval_id, None)


def peek_plan_resume(approval_id: str) -> PlanResume | None:
    with _lock:
        return _resumes.get(approval_id)


def clear_plan_resumes() -> None:
    """Test helper."""
    with _lock:
        _resumes.clear()
