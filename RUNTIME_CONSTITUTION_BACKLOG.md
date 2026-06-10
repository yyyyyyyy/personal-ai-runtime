# Runtime Constitution Backlog

> **Horizon:** 4 weeks  
> **Scope:** Boundary / Event Plane / Capability / Governed Domain convergence only  
> **Out of scope:** New features, new Agents, new Primitives, new Runtime layers

## Architecture Goals (Frozen)

1. Single Mutation Authority — governed domain writes only via `kernel.emit_event`
2. Single Event Plane — `event_log` is domain truth; no parallel domain writes
3. Capability-Centric Execution — all external interactions via `kernel.invoke_capability`
4. Agent demoted to Application Persona — no Kernel Agent expansion this sprint
5. Governed Domain = `goals` / `actions` / `tasks` / `memories` / `approvals`

---

## Sprint Status

| Sprint | Status | Notes |
|--------|--------|-------|
| **W1** | ✅ Complete | Runtime engines read via `query_state`; boundary CI hardened |
| **W2** | ✅ Complete | Agent hot path + Goals API + scheduler/trigger governed reads |
| **W3** | ✅ Complete | Single Execution Authority — invoke_capability + memory index |
| **W4** | ✅ Complete | Single Event Plane — event_log truth + Kernel→Bus bridge |

---

## Week 1 — Boundary Guard + Runtime Engine Reads ✅

- [x] W1-T1: `check_boundary.py` — governed SELECT detection (runtime engines)
- [x] W1-T2: `query_state` filters for tasks / approvals / memories
- [x] W1-T3: `task_engine`, `approval_engine`, `executor`, `memory_decay` migrated

---

## Week 2 — Agent Hot Path + Goals API Reads ✅

- [x] W2-T1: `context_engine`, `world_model`, `intent_predictor` — governed reads → `query_state`
- [x] W2-T2: `api/goals.py` — `/priorities/sorted`, `/stagnant` → `query_state`
- [x] W2-T3: `trigger_engine`, `scheduler_v2` — governed reads → `query_state`
- [x] W2-T4: `check_boundary` — removed W1 runtime allowlist; enforced on `api/`, `agents/`, `runtime/` (except `kernel/`)
- [x] W2-T5: `api/system.py` — goal/memory counts → `query_state` (CI green)
- [x] W2-T6: `query_state` goals/actions extensions + `GoalUpdated` supports explicit `last_activity_at`

**W2 exit criteria met:**
- Agent 热路径（Brain → context_engine → world_model → intent_predictor）无法 bypass governed 投影读
- `check_boundary.py` OK on full `api/` + `agents/` + `runtime/` scan scope
- `background_worker` / `self_improver` — 无 governed 读；保留 `db` 访问 Application Storage（`background_tasks`, `activity_log`）

---

## Week 3 — Capability + Memory Index Convergence ✅

- [x] W3-T1: `invoke_capability(pre_approved=True)` + `chat.resolve_approval` → Kernel only
- [x] W3-T2: `approval_engine` → `kernel.request_approval` / `grant_approval` / `deny_approval`
- [x] W3-T3: `_sync_memory_index` in Kernel; `memory_engine` Event-first only
- [x] W3-T4: `brain` → `kernel.list_capability_definitions()`; `check_boundary` bans `mcp_hub` import in User Space

**Exit criteria met:**
- Zero `mcp_hub` outside `kernel/` + `harness/`
- Zero `vector_store` in `core/agents/`
- All capability execution via `kernel.invoke_capability`

---

## Week 4 — Event Plane Convergence ✅

- [x] W4-T1: Remove governed dual-writes (`goals.py`, `executor.py`, `brain.py` tool_call)
- [x] W4-T2: Hot-path reads → `kernel.read_events` + `legacy_event_adapter` (`context_engine`, `world_model`, `api/events`, `api/goals`)
- [x] W4-T3: `kernel_event_bridge` in `main.py`; remove parallel publish from `task_engine`, `approval_engine`, `state_manager`, `executor`
- [x] W4-T4: Extend `kernel.read_events` (`since_ts`, `limit`, `order`)

**W4 exit criteria met:**
- Governed domain events write only to `event_log`
- Timeline / context reads served from `event_log` via legacy adapter (UI format unchanged)
- `scheduler_v2` dependency unlock driven by Kernel→Bus bridge (`TaskStatusChanged` → `TASK_COMPLETED`)
- `event_recorder` retained for Product (`morning_brief`) + Conversation (`brain.py`) only

---

## Explicit Non-Goals (Remaining Sprints)

- Conversation / messages Event Sourcing
- `background_tasks` merge into Task aggregate
- `spawn_agent` / `kill_agent` removal
- Product layer governed read migration (`product/`, `review_engine.py`) — post-W4 debt
- `core/telemetry/telemetry.py`, `core/scheduler.py` — post-W4 debt

---

## Top 5 Architecture Tasks (Updated)

| # | Task | Status |
|---|------|--------|
| 1 | Harden boundary CI | ✅ W1+W2 |
| 2 | Runtime engine reads → `query_state` | ✅ W1 |
| 3 | Agent hot-path governed reads | ✅ W2 |
| 4 | Capability + Memory index convergence | ✅ W3 |
| 5 | Event plane convergence | ✅ W4 |

---

## Verification Commands

```bash
python3 backend/scripts/check_boundary.py
python3 backend/scripts/verify_rebuild.py
python3 -m pytest backend/tests/runtime/ backend/tests/integration/ -q

# Governed read bypass in enforced scope (target: zero)
rg "SELECT .* FROM (goals|tasks|actions|memories|approvals)" backend/app/api backend/app/core/agents backend/app/core/runtime \
  --glob '!**/kernel/**'

# Execution authority (target: zero outside kernel + harness)
rg "mcp_hub" backend/app --glob '!**/kernel/**' --glob '!**/harness/**'
rg "from app\.store\.vector" backend/app/core/agents
```

---

## Known Debt (Outside W2 Scan Scope)

| path | reason |
|------|--------|
| `product/morning_brief.py` | Product layer — not in `api/agents/runtime` scan |
| `core/review_engine.py` | Core module — not in scan scope |
| `core/telemetry/telemetry.py` | Observability — W4+ |
| `core/scheduler.py` | Legacy scheduler — W4+ |
| `agents/memory_engine.py` | ✅ W3 — Kernel owns Chroma sync |
| `agents/conversation.py` | Application Storage |
| `agents/memory_v2.py` | Application Storage (`user_profile`) |
