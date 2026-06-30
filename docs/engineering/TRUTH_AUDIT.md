# Truth Audit Report — Cycle #2 (Incremental)

## Audit Metadata
- **Timestamp**: 2026-06-30 14:16:00 UTC
- **Repository**: personal-ai-runtime
- **Commit SHA**: 168895ca6a6b3f10e170e6ef1757503134a0f1bf (HEAD)
- **Working Tree**: CLEAN
- **Scope**: Incremental — diff from cycle #1 baseline (95297a8) to HEAD (168895c)
- **Previous Cycle**: `docs/engineering/TRUTH_AUDIT.md` (48 FACTs) + `docs/engineering/VERIFICATION_REPORT.md` (FACT Corrections)

## Pre-flight: FACT Corrections Consumed

From cycle #1 VERIFICATION_REPORT, the following correction was ingested:

| FACT ID | Original | Corrected | Action |
|---------|----------|-----------|--------|
| FACT-43 | `legacy_event_adapter = DORMANT/DEPRECATED` | **ACTIVE** — 3 production callers: `read_ports.py:16`, `goals.py:11`, `world_model.py:11` | Re-audited below as FACT-C2-01 |

---

## Source Diff Summary (95297a8 → 168895c)

| Category | Files | Change |
|----------|-------|--------|
| Modified | `constants.py` | Added deprecation comments to `EVENT_BELIEF_FORMED`, `AGGREGATE_PATTERN`, `MEMORY_INDEX_EVENT_TYPES` |
| Modified | `legacy_event_adapter.py` | Added deprecation docstring (same text as comments above) |
| Added | `test_query_state_w3.py` | 400 lines, 30 tests covering kernel query_state gaps |

No source code deletions, no API changes, no architectural refactoring occurred in this cycle.

---

## FACT-C2-01: legacy_event_adapter is ACTIVE — correction from cycle #1

**EVIDENCE**:
- `backend/app/core/runtime/legacy_event_adapter.py`, line 1: Module exists with DEPRECATED docstring added this cycle.
- `backend/app/core/runtime/read_ports.py`, line 16: `from app.core.runtime.legacy_event_adapter import recent_legacy_events`
- `backend/app/api/goals.py`, line 11: `from app.core.runtime.legacy_event_adapter import goal_legacy_events`
- `backend/app/core/agents/world_model.py`, line 11: `from app.core.runtime.legacy_event_adapter import to_legacy_dict`
- `backend/app/store/schema_ddl.py`: Legacy `events` table (APP_STORAGE) still exists in DDL — the target table for this adapter.

**CONFIDENCE**: HIGH

**RATIONALE**: Cycle #1 misclassified this as DORMANT/DEPRECATED-"可删". The correction is verified: 3 production modules import functions from this adapter. The deprecation docstring added this cycle clarifies intent but does not change the fact that the adapter is actively consumed. Any deletion plan (PR-06 in IMPLEMENTATION_PLAN.md) must first migrate all 3 callers.

**TYPE**: RUNTIME_ARCHITECTURE (correction)

**Downstream Impact**: S02 should update ADR/Roadmap to reflect that this adapter is ACTIVE, not DORMANT. S03 PR-06 deletion estimate must include migration of `goals.py` and `world_model.py`.

---

## FACT-C2-02: Deprecation comments added to constants.py — no semantic change

**EVIDENCE**:
- `backend/app/core/runtime/kernel/constants.py`, line 35: `EVENT_BELIEF_FORMED = "BeliefFormed"  # DEPRECATED — Pattern/Belief pipeline removed in v0.2 (H2); kept for event_log backward compat`
- `backend/app/core/runtime/kernel/constants.py`, line 113: `AGGREGATE_PATTERN = "pattern"  # DEPRECATED — Pattern pipeline removed in v0.2 (H2); kept for event_log backward compat`
- `backend/app/core/runtime/kernel/constants.py`, line 150: `EVENT_BELIEF_FORMED,  # DEPRECATED — no longer emitted post-v0.2; kept for backward compat`
- `backend/app/core/runtime/legacy_event_adapter.py`, lines 1-12: Full DEPRECATED docstring added.

**CONFIDENCE**: HIGH

**RATIONALE**: These are purely documentation additions. No imports, call sites, or behavior changed. Cycle #1 already identified `EVENT_BELIEF_FORMED` and `AGGREGATE_PATTERN` as dead code (FACT-38) — these comments merely make that status explicit in-code rather than only in documentation.

**TYPE**: DEAD_CODE (documented)

---

## FACT-C2-03: W3 test file adds 30 kernel-level tests (400 lines)

**EVIDENCE**:
- `backend/tests/runtime/test_query_state_w3.py`, 400 lines, 30 test methods across 5 test classes
- Coverage impact: kernel runtime coverage improved from 82% (640 miss) → 84% (570 miss)
- Specific coverage added: `_query_patterns`, `_query_notifications`, `_query_approvals`, `_query_inbox_emails`, `_query_policy_events`, `_query_grant_events`, `expire_stale_approvals`, `deny_approval`, `read_events` filters, `read_events_by_seqs`, `submit_command` timeout, `count_events`, `bootstrap_chat_from_snapshot`

**CONFIDENCE**: HIGH

**RATIONALE**: The file is the sole code addition in this cycle. It closed the CI coverage gap that existed at cycle #1's end.

**TYPE**: EXECUTION_FLOW (test coverage)

---

## FACT-C2-04: FACT-35 (approval read duplication), FACT-37 (notification dedup bug), FACT-45 (SQL builder duplication) — all UNCHANGED

**EVIDENCE**:
- `approval_engine.py` vs `kernel.py:_consume_pre_approved`: Both still query `approvals` independently. No PR executed.
- `background_worker.py:82-88`: Still passes `related_id`/`notification_type` to `_query_notifications` which does not support them.
- `kernel_query_state.py`: Still hand-writes WHERE clauses; `query_builder.py` still unused.

**CONFIDENCE**: HIGH

**RATIONALE**: No source code changes in these files across the cycle.

**TYPE**: DUPLICATION / DEAD_CODE (unchanged)

---

## FACT-C2-05: CI route check fixed — `/api/memory/profile` → `/api/memory/portrait`

**EVIDENCE**:
- `.github/workflows/ci.yml`, line 90: `'/api/memory/portrait'` (was `'/api/memory/profile'`)
- `backend/app/api/memory.py`, line 136: `@router.get("/portrait")` — endpoint was always correct; CI check was stale.

**CONFIDENCE**: HIGH

**RATIONALE**: CI configuration drift fix. No code behavior change.

**TYPE**: GOVERNANCE_SYSTEM (CI config)

---

## Cycle #2 Summary

| Category | New FACTs | Status change from cycle #1 |
|----------|-----------|------------------------------|
| FACT Corrections digested | 1 (FACT-43) | DORMANT → **ACTIVE** |
| Code changes confirmed | 3 (deprecation comments, test file, CI fix) | — |
| Unchanged debt confirmed | 3 (FACT-35, FACT-37, FACT-45) | STILL_DUP / STILL_BUG |

**No new deaths, no new dormancies, no regressions.** This cycle's changes are purely documentation + test coverage. The 12-PR implementation plan from cycle #1 remains unexecuted (only CI fix completed). All budget violations and architecture debt from cycle #1 carry forward unchanged.
