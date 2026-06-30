# Truth Audit Report

## Audit Metadata
- **Timestamp**: 2026-06-30 12:23:00 UTC
- **Repository**: personal-ai-runtime
- **Commit SHA**: 95297a8225ee3bc48b75ff8d975c3adc84ed32d0 (reference only)
- **Working Tree**: DIRTY (modified files present; audit is against working tree, not clean commit)
- **Scope**: Full repository scan (backend/, tests/, docs/)
- **Files Scanned**: ~234 Python files (126 source + 108 test), 30+ docs

---

## FACT 1: Kernel is the single write boundary (Event Sourcing)

**EVIDENCE**:
- `backend/app/core/runtime/kernel/kernel.py`, lines 79-188: `class Kernel(QueryStateMixin, GovernanceMixin, SovereigntyMixin)` — the single class that touches `self._db`. `emit_event()` method (line 108) inserts into `event_log` (line 162-179), runs `projectors.apply(event, conn)` synchronously in the same transaction (line 184), then dispatches to subscribers and AgentBus.
- `backend/app/core/runtime/kernel_instance.py`, line 10: `kernel = Kernel()` — global singleton; User Space must import this, never instantiate Kernel directly.
- `backend/app/core/runtime/kernel/__init__.py`, lines 3-7: docstring states "the boundary of the Runtime. User Space talks to the system exclusively through Kernel; only the Kernel touches storage."

**CONFIDENCE**: HIGH

**RATIONALE**: The code enforces this through design — `Kernel.emit_event()` is the only write entry point with an explicit append-only `event_log` INSERT. All projectors run synchronously within the same SQLite transaction. The docstring and kernel_instance.py both explicitly state this boundary.
**TYPE**: RUNTIME_ARCHITECTURE

---

## FACT 2: FastAPI Application serves as the HTTP entry point with custom ASGI AuthMiddleware

**EVIDENCE**:
- `backend/app/main.py`, lines 273-294: FastAPI app creation with `lifespan` context manager.
- `backend/app/main.py`, lines 86-102: `class AuthMiddleware` — `__call__` method checks if `scope["type"] != "http"` (returns early for WebSocket), validates Bearer token, skips whitelisted paths.
- `backend/app/main.py`, line 47: `SKIP_AUTH_PATHS` includes `/`, `/api/system/health`, `/api/system/live`, `/docs`, `/redoc`, `/openapi.json`.
- `backend/app/main.py`, lines 296-305: Middleware registration order: `AuthMiddleware` first, then `CORSMiddleware`.

**CONFIDENCE**: HIGH

**RATIONALE**: The middleware implementation is clear and complete. The ASGI design choice (not BaseHTTPMiddleware) is explicitly for SSE streaming compatibility. CORSMiddleware is registered after AuthMiddleware per standard FastAPI recommendations.
**TYPE**: RUNTIME_ARCHITECTURE

---

## FACT 3: RuntimeContainer is a lazy-loaded subsystem registry with 12+ components

**EVIDENCE**:
- `backend/app/core/runtime/runtime_container.py`, lines 30-141: `RuntimeContainer` with properties for `kernel` (line 50), `capability_gateway` (line 64), `capability_policy` (line 72), `taint_registry` (line 80), `agent_bus` (line 88), `approval_engine` (line 96), `context_pipeline` (line 104), `task_engine` (line 112), `trigger_engine` (line 118), `background_worker` (line 122).
- Lines 130-138: `reset()` method clears agent_bus, capability_policy, source_registry, external_tools for test isolation.

**CONFIDENCE**: HIGH

**RATIONALE**: Every property uses the same lazy-initialization pattern. The `_inventory` list tracks all registered subsystems for observability.
**TYPE**: RUNTIME_ARCHITECTURE

---

## FACT 4: Kernel inherits from three Mixin classes via multiple inheritance

**EVIDENCE**:
- `backend/app/core/runtime/kernel/kernel.py`, line 79: `class Kernel(QueryStateMixin, GovernanceMixin, SovereigntyMixin):`
- `backend/app/core/runtime/kernel/_mixin_protocol.py`, lines 16-54: `class _KernelMixinInterface(Protocol)` defines the interface expected by mixins.
- `backend/app/core/runtime/kernel/kernel_query_state.py`, lines 14-43: `QueryStateMixin.query_state(selector, **filters)` dispatches to 12 `_query_*` methods.
- `backend/app/core/runtime/kernel/kernel_governance.py`, lines 24-152: `GovernanceMixin` with `request_approval()`, `expire_stale_approvals()`, `grant_approval()`, `deny_approval()`.

**CONFIDENCE**: HIGH

**RATIONALE**: The MRO is explicit in the code. Each mixin file is independently readable and uses the Protocol to establish its contract with Kernel.
**TYPE**: RUNTIME_ARCHITECTURE

---

## FACT 5: Projectors use a global registry with @projector decorator

**EVIDENCE**:
- `backend/app/core/runtime/kernel/projectors_registry.py`, lines 17-43: `_HANDLERS: dict[str, Handler] = {}`, `@projector(*event_types)` decorator, `apply(event, conn)` function.
- `backend/app/core/runtime/kernel/projectors.py`, lines 7-18: Imports all projector sub-modules to trigger `@projector` registrations across 7 modules.
- `backend/app/core/runtime/kernel/projectors_core.py`, line 9: `_OWNED_TABLES["goal"] = ["goals"]` — each projector module declares its owned tables.

**CONFIDENCE**: HIGH

**RATIONALE**: The registry pattern is clear and decomposed across seven projector modules. Each projector module declares its owned tables via `_OWNED_TABLES`.
**TYPE**: RUNTIME_ARCHITECTURE

---

## FACT 6: Chat API emits ChatRequested event, SSE consumes via in-memory queue

**EVIDENCE**:
- `backend/app/api/chat.py`, lines 83-120: `send_message()` creates correlation_id, ensures agent, registers SSE queue, emits `ChatRequested`.
- `backend/app/api/chat.py`, lines 122-177: `sse_stream()` inner generator reads from `sse_queue` with 0.1s timeout, 15s heartbeats, falls back to event_log polling.
- `backend/app/api/chat.py`, lines 70-73: `ChatTextDelta` constant comment says "DELIBERATELY NOT EMITTED TO EVENT_LOG — pushed to SSE queue to avoid polluting Truth Layer".
- `backend/app/core/runtime/kernel/constants.py`, line 70: `EVENT_CHAT_TEXT_DELTA = "ChatTextDelta"` with matching docstring.

**CONFIDENCE**: HIGH

**RATIONALE**: The dual delivery path is clearly documented: event_log for audit/truth, SSE queue for low-latency text streaming. The SSE generator's fallback to event_log polling provides robustness.
**TYPE**: EXECUTION_FLOW

---

## FACT 7: Scheduler drives WorkItem state machine with Execution aggregate events

**EVIDENCE**:
- `backend/app/core/runtime/agent_scheduler.py`, lines 22-25: State machine docstring: `pending -> running -> completed`, with retry path.
- Lines 147-158: `_emit_verify(item, emit_fn)` — emits Execution* event then calls `verify_persist_matches_projection`.
- Lines 229-270: `_process_work_item()` — transitions to running, executes handler with timeout.
- Lines 70-116: `_recover()` — reads running/pending items from projection, transitions interrupted items to retrying.
- Line 49: `_MAX_CONCURRENT = 8`; line 65: `_tick_interval = 0.05` seconds.

**CONFIDENCE**: HIGH

**RATIONALE**: The scheduler is the central execution engine. Its state machine, retry logic, recovery, and the projector-verifier pattern are all clearly implemented.
**TYPE**: EXECUTION_FLOW

---

## FACT 8: AgentBus provides async pub/sub dispatch on top of the Event Log

**EVIDENCE**:
- `backend/app/core/runtime/agent_bus.py`, lines 43-190: `class AgentBus` with `subscribe()`, `unsubscribe()`, `publish()`, `deliver_to()`, `reset()`.
- Lines 120-139: `publish()` resolves subscriptions, puts events on per-agent queues, invokes handlers directly.
- Lines 152-167: `_rule_matches()` checks event_type via `fnmatch`, aggregate_type equality, source_agent prefix, correlation_match prefix.
- `backend/app/core/runtime/kernel/kernel.py`, lines 467-495: `_dispatch()` creates asyncio task for `agent_bus.publish(event)` with done_callbacks for error logging.

**CONFIDENCE**: HIGH

**RATIONALE**: The architectural comment states AgentBus is NOT a new infrastructure layer but a SubscriptionManager on top of the Event Log. Pattern-matching and dual-delivery mechanisms are well-implemented.
**TYPE**: RUNTIME_ARCHITECTURE / EXECUTION_FLOW

---

## FACT 9: Bootstrap ensures a single persistent AgentInstance for event routing

**EVIDENCE**:
- `backend/app/core/runtime/agent_bootstrap.py`, lines 13-38: `ensure_agent()` sets `_spawned = True` after first call, spawns `CHAT_DEFINITION`, subscribes 6 handlers to AgentBus.
- `backend/app/core/agents/mvp/__init__.py`, lines 23-34: `CHAT_DEFINITION = AgentDefinition(agent_id="chat_v1", tools=["*"], subscriptions=[...])`.
- `backend/app/core/runtime/agent_instance.py`, lines 167-189: `dispatch()` creates WorkItem via `scheduler.enqueue(self.instance_id, self.actor_id(), event)`.

**CONFIDENCE**: HIGH

**RATIONALE**: The bootstrap pattern is explicitly called in chat.py (line 101), background_worker.py (line 146), and bypass_handlers.py. There is only one agent instance for all event types.
**TYPE**: EXECUTION_FLOW

---

## FACT 10: Chat execution flow is a 5-stage pipeline

**EVIDENCE**:
- Stage 1 (`backend/app/api/chat.py`, lines 83-120): API emits `ChatRequested` + creates SSE queue.
- Stage 2 (`backend/app/core/runtime/kernel/kernel.py`, lines 467-495): `_dispatch()` publishes to AgentBus.
- Stage 3 (`backend/app/core/runtime/agent_instance.py`, lines 167-189): `dispatch()` enqueues WorkItem.
- Stage 4 (`backend/app/core/agents/mvp/chat_handler.py`, lines 26-117): `on_chat_requested` compiles prompt, runs `Brain.chat_stream()`, pushes text deltas, emits ChatCompleted + ChatDone.
- Stage 5 (`backend/app/core/agents/brain.py`, lines 40-266): `Brain.chat_stream()` manages LLM tool-call loop with multi-provider failover, telemetry, memory extraction.

**CONFIDENCE**: HIGH

**RATIONALE**: The full call chain is traceable from FastAPI endpoint to event emission. Each stage is independently verifiable in the source code.
**TYPE**: EXECUTION_FLOW

---

## FACT 11: Capability invocation has a 4-gate authorization model

**EVIDENCE**:
- `backend/app/core/runtime/capability_decision.py`, lines 30-122: `CapabilityGateway.decide()` implementing gates 1-4.
- Gate 1 (lines 58-64): `capability_policy.risk_for()` returns `"forbidden"` → deny.
- Gate 2 (lines 66-69): agent principals checked via `_principal_has_grant()`.
- Gate 3 (lines 72-86): pre-approved fast path with `_consume_pre_approved()`.
- Gate 4 (lines 88-106): risk assessment via `sensitive_router.elevated_risk()`, taint check, non-user principal auto-deny on high risk.
- `backend/app/core/runtime/kernel/kernel.py`, lines 601-745: `kernel.invoke_capability()` resolves principal, calls `capability_gateway.decide()`, handles allow/deny/defer.

**CONFIDENCE**: HIGH

**RATIONALE**: The gate model is explicitly documented in comments (lines 33-37). Each gate has a distinct code path with clear return values.
**TYPE**: EXECUTION_FLOW

---

## FACT 12: Timer Engine scans every 1 second and emits TimerFired events with 8 cron schedules

**EVIDENCE**:
- `backend/app/core/runtime/timer_engine.py`, lines 90-203: `TimerEngine` with `_loop()`, `_check_and_fire()`.
- Line 27: `_SCAN_INTERVAL = 1.0` seconds.
- Lines 127-176: `_check_and_fire()` queries `timer_events` for active timers, emits `TimerFired`, recalculates next cron fire.
- `backend/app/core/runtime/cron_registry.py`, lines 25-34: `SCHEDULES` list with 8 entries (morning_brief, deadline_alert, trigger_evaluation, memory_decay, world_model_snapshot, projection_snapshots, inbox_poll, inbox_digest).
- `backend/app/core/agents/mvp/timer_trigger_handler.py`, lines 140-147: `on_timer_fired` dispatches to 8 product functions.

**CONFIDENCE**: HIGH

**RATIONALE**: The timer engine is fully event-sourced: TimerCreated creates the projection, TimerEngine reads it, TimerFired triggers handlers.
**TYPE**: EXECUTION_FLOW

---

## FACT 13: BackgroundWorker polls background_tasks table every 10 seconds

**EVIDENCE**:
- `backend/app/core/runtime/background_worker.py`, lines 22-197: `BackgroundWorker` with `_poll_loop()`.
- Lines 44-53: `_poll_loop()` runs 4 methods sequentially each cycle, sleeps 10 seconds.
- Lines 64-120: `_smart_notification_check()` checks for stagnant goals (3+ days).
- Lines 132-157: `_execute_background_task()` calls `kernel.submit_command("BackgroundTaskRequested", ...)`.

**CONFIDENCE**: HIGH

**RATIONALE**: The poll loop is clearly structured. The background worker is started in the FastAPI lifespan (main.py line 216).
**TYPE**: EXECUTION_FLOW

---

## FACT 14: submit_command provides synchronous event-response pattern with async Future

**EVIDENCE**:
- `backend/app/core/runtime/kernel/kernel.py`, lines 190-260: `submit_command()` creates a Future keyed by `(correlation_id, completion_type)`, emits the event, waits via `asyncio.wait_for()`, default timeout 60s.
- Lines 497-520: `_dispatch()` resolves `_pending_commands` futures when matching completion events arrive.
- Lines 522-539: Special handling: `BackgroundTaskFailed` also resolves `BackgroundTaskCompleted` waiters.
- Lines 252-260: `finally` block guarantees cleanup of pending command registration.

**CONFIDENCE**: HIGH

**RATIONALE**: The contract is well-defined: correlation_id links request to completion event. Edge cases (no running event loop, BackgroundTaskFailed) are handled.
**TYPE**: EXECUTION_FLOW

---

## FACT 15: Notification bridge supports both sync and async contexts

**EVIDENCE**:
- `backend/app/core/runtime/notification_bridge.py`, lines 25-86: `push_notification()` (persists + broadcasts) and `broadcast_event()` (pure transport, no persistence).
- Lines 48-71: `broadcast_event()` auto-detects execution context: async → `loop.create_task()`, sync → `asyncio.run()`.
- `backend/app/main.py`, lines 42-43: `_ws_connections: list[WebSocket]` and `_ws_lock = Lock()` manage WebSocket connections.

**CONFIDENCE**: HIGH

**RATIONALE**: The dual-context dispatch is explicitly documented in the module docstring. The sync/async divergence is described as differing only in *when* the WebSocket write happens.
**TYPE**: EXECUTION_FLOW

---

## FACT 16: Legacy event adapter maps event_log to deprecated events-table shape

**EVIDENCE**:
- `backend/app/core/runtime/legacy_event_adapter.py`, lines 1-9: Module docstring states DEPRECATED with removal target v0.3.0.
- Lines 18-36: `_LEGACY_TYPE` dict maps 18 Kernel event types to legacy types.
- Lines 91-101: `to_legacy_dict(event)` converts Event to legacy row shape.
- Lines 145-190: `recent_legacy_events()` is the main public function, accepts `read_fn` (kernel.read_events).

**CONFIDENCE**: HIGH

**RATIONALE**: The deprecation status is clearly marked. The adapter provides a complete mapping layer with reverse lookup (`_LEGACY_TO_KERNEL`) for backward-compatible queries.
**TYPE**: RUNTIME_ARCHITECTURE

---

## FACT 17: HandlerRegistry uses @subscribe decorator with 6 registered handlers

**EVIDENCE**:
- `backend/app/core/runtime/handler_registry.py`, lines 22-74: `_registry: dict[str, Handler] = {}`, `@subscribe` decorator, `get_handler()`, `registered_types()`.
- `backend/app/core/agents/mvp/chat_handler.py`, line 26: `@subscribe("ChatRequested")`.
- `backend/app/core/agents/mvp/bypass_handlers.py`, lines 25, 105, 172, 265: `@subscribe` on `on_approve_requested`, `on_execute_requested`, `on_bg_task_requested`, `on_inbox_poll_requested`.
- `backend/app/core/agents/mvp/timer_trigger_handler.py`, line 140: `@subscribe("TimerFired")`.
- `backend/app/core/agents/mvp/__init__.py`, lines 15-19: Handler modules imported to trigger `@subscribe` registrations.

**CONFIDENCE**: HIGH

**RATIONALE**: The separation between HandlerRegistry (async business logic) and ProjectorRegistry (sync state materialization) is a key architectural distinction. Handlers are loaded via module import side effects.
**TYPE**: RUNTIME_ARCHITECTURE

---

## FACT 18: ExecutionContext provides scoped handler identity via ContextVar

**EVIDENCE**:
- `backend/app/core/runtime/execution_context.py`, lines 25-62: `@dataclass class ExecutionContext` with `emit()` method.
- `backend/app/core/runtime/execution_scope.py`, lines 1-34: `_current_execution_id: ContextVar`, `execution_scope()` context manager, `actor_requires_execution_ownership()`.
- `backend/app/core/runtime/kernel/kernel.py`, lines 635-653: `invoke_capability()` checks execution ownership, emits `CapabilityDenied` on validation failure.

**CONFIDENCE**: HIGH

**RATIONALE**: The ContextVar pattern enables implicit execution ID propagation through async handler call chains. Runtime ownership actors are explicitly defined in a set.
**TYPE**: RUNTIME_ARCHITECTURE

---

## FACT 19: Lifespan initializes 6 subsystems in ordered sequence

**EVIDENCE**:
- `backend/app/main.py`, lines 172-268: Full `lifespan()` async context manager.
- Line 175: `run_startup_checks()`.
- Line 209: `init_scheduler()`.
- Lines 212-214: `capability_policy.seed_from_json(kernel)`.
- Line 216: `await background_worker.start()`.
- Lines 218-220: `trigger_engine.seed_builtin_triggers()`.
- Lines 222-229: `await start_mcp_mesh()`.
- Lines 246-268: Shutdown in reverse order: MCP mesh stop, background worker stop, scheduler shutdown, WebSocket close.

**CONFIDENCE**: HIGH

**RATIONALE**: The lifespan is the single orchestration point for startup/shutdown. The ordering is explicit. MCP mesh failure is caught and logged, allowing the runtime to continue with builtin tools only.
**TYPE**: EXECUTION_FLOW

---

## FACT 20: StateManager validates task state transitions via a hardcoded FSM

**EVIDENCE**:
- `backend/app/core/runtime/state_manager.py`, lines 9-28: `TaskStatus` enum with 7 states, `_TRANSITIONS` dict mapping each state to allowed next states.
- Lines 34-41: `validate_transition()` returns True or raises ValueError.
- Lines 43-46: `transition()` calls validate then returns new status (side-effect-free).
- `backend/app/core/runtime/task_engine.py`, lines 87-104: `update_task_status()` calls `state_manager.transition()`, then emits `TaskStatusChanged`.

**CONFIDENCE**: HIGH

**RATIONALE**: The FSM is hardcoded and complete. Terminal states (`COMPLETED`, `CANCELLED`) have empty allowed sets.
**TYPE**: RUNTIME_ARCHITECTURE

---

## FACT 21: Memory storage uses dual architecture — SQLite projection + ChromaDB vector index

**EVIDENCE**:
- `backend/app/store/schema_ddl.py`, lines 4-17: `memories` table with columns: `id`, `category`, `content`, `source`, `embedding_id`, `confidence`, `derived_from_event`, `decayed_at`, `status`, `origin`, `claim_status`, `created_at`.
- `backend/app/store/vector.py`, lines 28-117: `VectorStore` manages two ChromaDB collections: `"memories"` and `"knowledge"`, backed by `chromadb.PersistentClient`.
- `backend/app/core/agents/memory_engine.py`, lines 3-5: Docstring states "ChromaDB is a derived search index maintained by the Kernel after projection."

**CONFIDENCE**: HIGH

**RATIONALE**: Both storage mechanisms are explicitly defined. The relationship is documented in MemoryEngine: ChromaDB is a derived index, not the source of truth.
**TYPE**: MEMORY_SYSTEM

---

## FACT 22: Memory writes are exclusively event-sourced through the Kernel

**EVIDENCE**:
- `backend/app/core/agents/memory_engine.py`, lines 16-39: `store_memory()` calls `kernel.emit_event(type="MemoryDerived", ...)` — never touches the DB directly.
- Lines 87-94: `delete_memory()` calls `kernel.emit_event(type="MemoryDeleted", ...)`.
- Lines 96-113: `update_memory()` calls `kernel.emit_event(type="MemoryUpdated", ...)`.
- `backend/app/core/runtime/kernel/projectors_core.py`, line 137: `_OWNED_TABLES["memory"] = ["memories"]` — declares exclusive Kernel ownership.

**CONFIDENCE**: HIGH

**RATIONALE**: Every write path in MemoryEngine routes through `kernel.emit_event()`. The `_OWNED_TABLES` registration declares exclusive Kernel ownership of the table.
**TYPE**: MEMORY_SYSTEM

---

## FACT 23: ChromaDB index synchronization happens in two phases

**EVIDENCE**:
- Phase 1 (`backend/app/core/runtime/kernel/kernel.py`, lines 138-160): In `emit_event()`, pre-computes the ChromaDB embedding by calling `vector_store.delete_memory(aggregate_id)` then `vector_store.add_memory(...)`, stores `embedding_id` in event payload.
- Phase 2 (lines 262-306): `_sync_memory_index()` runs after SQL transaction commits. Retries failed embeddings. On `MemoryDeleted`, removes from ChromaDB. Pushes `memory_changed` SSE notification on success.

**CONFIDENCE**: HIGH

**RATIONALE**: Both methods are present with clear comments. The pre-compute eliminates the cross-connection UPDATE that previously happened in _sync_memory_index after commit.
**TYPE**: MEMORY_SYSTEM

---

## FACT 24: Memory confidence operates on a [0, 1] scale with initial default of 0.5

**EVIDENCE**:
- `backend/app/core/agents/memory_engine.py`, line 22: `confidence: float = 0.5` default parameter.
- `backend/app/core/runtime/kernel/projectors_core.py`, line 183: `p.get("confidence", 0.5)`.
- `backend/app/store/schema_ddl.py`, line 10: `confidence REAL DEFAULT 0.5`.

**CONFIDENCE**: HIGH

**RATIONALE**: The value 0.5 is consistent across all three locations: engine parameter default, projector fallback, and schema default.
**TYPE**: MEMORY_SYSTEM

---

## FACT 25: Memory decay is a scheduled cron job (daily at 3:00 AM)

**EVIDENCE**:
- `backend/app/core/runtime/cron_registry.py`, line 29: `{"name": "memory_decay", "cron_expr": "hour=3,minute=0", "schedule_type": "cron", "handler_name": "memory_decay"}`.
- `backend/app/core/runtime/memory_decay.py`, lines 13-35: `run_memory_decay()` queries memories with `confidence_gt=0.1, confidence_lt=0.8, decay_eligible=True, limit=50`, decays those below threshold=0.3 by subtracting 0.1 (min 0.1).

**CONFIDENCE**: HIGH

**RATIONALE**: The cron schedule and decay logic have clear threshold parameters. The limit of 50 candidates per run is a hard-coded cap.
**TYPE**: MEMORY_SYSTEM

---

## FACT 26: There are TWO separate profile/memory stores — event-sourced `memories` + direct-SQLite `user_profile`

**EVIDENCE**:
- `backend/app/core/agents/user_profile.py`, lines 11-90: `UserProfile` writes directly to a `user_profile` SQLite table (INSERT OR REPLACE, SELECT, UPDATE) — bypasses the Kernel entirely.
- Manages structured categories: `["preferences", "values", "relationships", "health", "finance", "career"]` (line 8).
- `backend/app/api/memory.py`, lines 136-192: `/api/memory/portrait` endpoint combines data from both `user_profile.get_profile()` AND `memory_engine.list_memories()`.

**CONFIDENCE**: HIGH

**RATIONALE**: `UserProfile` uses direct `db.get_db()` calls, not `kernel.emit_event()`. This is a clear architectural deviation from the event-sourced memory path.
**TYPE**: MEMORY_SYSTEM

---

## FACT 27: All 37 builtin tools are registered in single MCPHub singleton as flat dict

**EVIDENCE**:
- `backend/app/core/harness/mcp_hub.py`, lines 39-43: `self._tools: dict[str, ToolDef] = {}`.
- Line 738: Global singleton `mcp_hub = MCPHub()`.
- Line 673: `register_tool()` inserts into `self._tools[tool.name]`.
- 37 builtin tools registered across 13 categories (time: 1, filesystem: 5, web: 2, calendar: 3, email: 3, browser: 2, clipboard_ocr: 2, shell: 1, git: 3, telegram: 2, goals: 4, computer_use: 7, voice: 2).

**CONFIDENCE**: HIGH

**RATIONALE**: All registration paths feed into this single dict. No sharding, no namespacing.
**TYPE**: TOOL_SYSTEM

---

## FACT 28: External MCP tools are discovered via stdio subprocess connections

**EVIDENCE**:
- `backend/app/core/harness/mcp_mesh.py`, lines 97-371: `MCPMesh` manages stdio `_ServerConnection` objects.
- Lines 50-73: `_ServerConnection.connect()` spawns subprocess via `stdio_client()`, initializes `ClientSession`, calls `session.list_tools()`.
- `backend/app/core/harness/mcp_config.py`, lines 127-167: `load_external_server_configs()` loads from `mcp_config.json`.
- Line 220: Lazy connection for servers with `startup_connect=False`.

**CONFIDENCE**: HIGH

**RATIONALE**: Full MCP stdio protocol discovery is implemented with timeout handling, lazy connect, and error resilience.
**TYPE**: TOOL_SYSTEM

---

## FACT 29: Tool execution follows single entry point: kernel.invoke_capability() → capability_gateway.decide() → mcp_hub.invoke_tool()

**EVIDENCE**:
- `backend/app/core/runtime/kernel/kernel.py`, lines 601-800: `kernel.invoke_capability()` — entry point.
- `backend/app/core/runtime/capability_decision.py`, lines 41-122: `capability_gateway.decide()` — 4-gate authorization.
- `backend/app/core/harness/mcp_hub.py`, lines 703-734: `mcp_hub.invoke_tool()` — execution.
- `backend/app/core/agents/tool_dispatcher.py`, lines 22-136: `ToolDispatcher` batch orchestrator.

**CONFIDENCE**: HIGH

**RATIONALE**: The complete chain from Brain → ToolDispatcher.dispatch() → kernel.invoke_capability() → mcp_hub.invoke_tool() is fully traceable.
**TYPE**: TOOL_SYSTEM / EXECUTION_FLOW

---

## FACT 30: Taint tracking uses ContextVar as async-safe store — not a database table

**EVIDENCE**:
- `backend/app/core/runtime/taint.py`, lines 54-57: `_taint_marks = contextvars.ContextVar[dict[str, dict[str, Any]] | None]`.
- Line 70: `TaintRegistry.mark()` stores `{correlation_id: {"source": ..., "reason": ...}}`.
- Line 83: `TaintRegistry.clear()` removes by correlation_id.
- Lines 16-23: 6 builtin tools classified as "external ingestion" (`check_inbox`, `read_inbox_email`, `web_search`, `fetch_url`, `search_and_extract`, `open_web_page`).
- Lines 41-51: 9 tools classified as "write class" (`apply_patch`, `write_file`, `add_calendar_event`, `send_email`, `shell_exec`, `telegram_send`, `computer_click`, `computer_type`, `computer_key`).

**CONFIDENCE**: HIGH

**RATIONALE**: ContextVar is inherently process-local and task-scoped. No persistence. The taint → approval escalation is coded in `capability_gateway.decide()`.
**TYPE**: TOOL_SYSTEM

---

## FACT 31: Tool results are truncated at 8000 characters before returning to LLM

**EVIDENCE**:
- `backend/app/core/harness/mcp_hub.py`, lines 723-724:
  ```python
  if isinstance(result, str) and len(result) > 8000:
      result = result[:8000] + "\n... [output truncated]"
  ```

**CONFIDENCE**: HIGH

**RATIONALE**: The truncation logic is explicit in `invoke_tool()`.
**TYPE**: TOOL_SYSTEM

---

## FACT 32: CapabilityGateway is the single authorization decision point

**EVIDENCE**:
- `backend/app/core/runtime/capability_decision.py`, lines 41-122: `CapabilityGateway.decide()` is the ONLY authorization entry point, called from `Kernel.invoke_capability()` at kernel.py:671-680.
- The `CapabilityGateway` singleton is registered in `RuntimeContainer.inventory()`.

**CONFIDENCE**: HIGH

**RATIONALE**: Code path is singular and well-defined. `invoke_capability` unconditionally calls `capability_gateway.decide()`.
**TYPE**: GOVERNANCE_SYSTEM

---

## FACT 33: No feature flag system exists anywhere in the codebase

**EVIDENCE**: Comprehensive search for `feature_flag`, `FEATURE_FLAG`, `feature_toggle`, and related patterns across all backend Python files returned zero matches. The `app_settings` table stores LLM config, email config, and custom prompts only — no flag/toggle schema exists.

**CONFIDENCE**: HIGH

**RATIONALE**: Exhaustive grep across all Python files with multiple pattern variants.
**TYPE**: GOVERNANCE_SYSTEM

---

## FACT 34: Audit events use fragmented logging patterns across 6+ modules

**EVIDENCE**:
- `backend/app/core/runtime/runtime_config.py`, lines 274-287: `AppConfigChanged` event.
- `backend/app/api/workflows.py`, lines 26-44: `WorkflowChanged` event.
- `backend/app/core/runtime/trigger_engine.py`, lines 164, 189: `TriggerCreated` / `TriggerDeleted` events.
- `backend/app/core/runtime/egress/egress_gate.py`, lines 47-69: `EgressApproved` event.
- `backend/app/core/runtime/conversation_recorder.py`, lines 21-50: `ConversationRecorded` event.
- `backend/app/activity_log.py`, lines 11-14: `log_activity()` function, called only from `event_recorder.py:63`.

There is no unified audit logging interface or policy.

**CONFIDENCE**: HIGH

**RATIONALE**: Each audit path was verified by reading source files. All six audit emission points are in different modules with different conventions.
**TYPE**: GOVERNANCE_SYSTEM

---

## FACT 35: Approval governance is dual-path (kernel-mixin + query-engine)

**EVIDENCE**:
- `backend/app/core/runtime/kernel/kernel_governance.py`, lines 24-153: `GovernanceMixin` provides `request_approval()`, `grant_approval()`, `deny_approval()`, `expire_stale_approvals()` — write paths.
- `backend/app/core/runtime/approval_engine.py`, lines 9-125: `ApprovalEngine` provides `get_approval()`, `list_pending()`, `list_all()` — read paths.
- `backend/app/core/runtime/kernel/kernel.py`, lines 557-591: `_consume_pre_approved()` ALSO reads approvals via `self.query_state("approvals", id=approval_id)`, bypassing `ApprovalEngine`.

**CONFIDENCE**: HIGH

**RATIONALE**: The read concern is split between Kernel and ApprovalEngine with no clear boundary enforcement.
**TYPE**: GOVERNANCE_SYSTEM / DUPLICATION

---

## FACT 36: ContextPolicy Protocol + governance snapshots are never consumed by DefaultContextPolicy

**EVIDENCE**:
- `backend/app/core/runtime/governance/context_policy.py`, lines 92-105: `ContextPolicy` Protocol declares `evaluate()` with optional `execution_context` and `capability_context`.
- Lines 122-135: `DefaultContextPolicy.evaluate()` accepts ONLY `request: CompileRequest` (no `**kwargs`).
- `backend/app/core/runtime/governance/context_pipeline.py`, line 130: calls `self._policy.evaluate(request)` without passing either context.
- `backend/app/core/runtime/governance/execution_context.py`, lines 101-195: `ExecutionContextProvider.build()` is fully implemented but has ZERO production callers.
- `backend/app/core/runtime/governance/capability_context.py`, lines 168-240: `CapabilityContextProvider.build()` is fully implemented but has ZERO production callers.

**CONFIDENCE**: HIGH

**RATIONALE**: The snapshot builders in execution_context.py and capability_context.py have zero callers in the production path.
**TYPE**: GOVERNANCE_SYSTEM / DORMANT_COMPONENT

---

## FACT 37: `_smart_notification_check` passes unsupported filters to `query_state` — silent no-op dedup

**EVIDENCE**:
- `backend/app/core/runtime/background_worker.py`, lines 82-87: calls `kernel.query_state("notifications", related_id=goal_id, notification_type="goal_stagnant", limit=1)`.
- `backend/app/core/runtime/kernel/kernel_query_state.py`, lines 287-329: `_query_notifications` only processes `id`, `type`, `title`, `unread_only`, `created_on_date`, `limit`, `order`. Does NOT process `related_id` or `notification_type`.
- Python silently ignores unrecognized kwargs, so the query returns ALL recent notifications unfiltered.

**CONFIDENCE**: HIGH

**RATIONALE**: Direct line-by-line comparison of the caller's kwargs against the callee's filter-key whitelist confirms the mismatch.
**TYPE**: DUPLICATION

---

## FACT 38: `EVENT_BELIEF_FORMED` and `AGGREGATE_PATTERN` are deprecated and never emitted

**EVIDENCE**:
- `backend/app/core/runtime/kernel/constants.py`, line 35: `EVENT_BELIEF_FORMED = "BeliefFormed"` with `# DEPRECATED — Pattern/Belief pipeline removed in v0.2 (H2); kept for event_log backward compat`.
- Line 113: `AGGREGATE_PATTERN = "pattern"` with identical deprecation note.
- `backend/app/store/schema_ddl.py`, line 189: Legacy `patterns` table still exists.
- Zero emit sites found by exhaustive search.

**CONFIDENCE**: HIGH

**RATIONALE**: Code comments explicitly state removal in v0.2. Zero callers found.
**TYPE**: DEAD_CODE

---

## FACT 39: `EVENT_AGENT_SPAWNED` and `EVENT_AGENT_TERMINATED` are declared but never used

**EVIDENCE**:
- `backend/app/core/runtime/kernel/constants.py`, lines 19-20:
  ```python
  EVENT_AGENT_SPAWNED = "AgentSpawned"      # UNUSED — reserved for future multi-agent lifecycle
  EVENT_AGENT_TERMINATED = "AgentTerminated"  # UNUSED — reserved for future multi-agent lifecycle
  ```
- `backend/app/core/runtime/agent_registry.py`, lines 63-111: `AgentRegistry.spawn()` emits `GrantCreated` events but does not emit `AgentSpawned`.

**CONFIDENCE**: HIGH

**RATIONALE**: Constants themselves are annotated as `UNUSED`. No emit sites found.
**TYPE**: DEAD_CODE

---

## FACT 40: `legacy_event_adapter._APPLICATION_EVENT_TYPES` is empty frozenset — typed queries always return empty

**EVIDENCE**:
- `backend/app/core/runtime/legacy_event_adapter.py`, line 49: `_APPLICATION_EVENT_TYPES: frozenset[str] = frozenset()`.
- Lines 111-125: `_application_legacy_events()` checks `if event_type not in _APPLICATION_EVENT_TYPES: return []`, so any typed query always returns empty.

**CONFIDENCE**: HIGH

**RATIONALE**: Empty frozenset combined with membership check guarantees `[]` return.
**TYPE**: DEAD_CODE

---

## FACT 41: `context_runtime.estimate_tokens()` is deprecated but still in fallback path

**EVIDENCE**:
- `backend/app/context_runtime.py`, lines 43-49:
  ```python
  def estimate_tokens(text: str) -> int:
      """DEPRECATED: 对于 budget 决策，优先使用 token_counter.count_text_tokens"""
      return max(1, len(text) // 4)
  ```
- Lines 36-38: `FragmentResult.__post_init__` still calls this when `token_count == 0`.

**CONFIDENCE**: HIGH

**RATIONALE**: Function explicitly marked as DEPRECATED in docstring. Still has one call site.
**TYPE**: DEAD_CODE

---

## FACT 42: `activity_log.log_activity()` is a near-dead abstraction with a single caller

**EVIDENCE**:
- `backend/app/activity_log.py`, lines 11-14: provides `log_activity()` that calls `db.log_activity()`.
- Only one production caller: `backend/app/core/telemetry/event_recorder.py`, line 63.
- All other audit paths use `kernel.emit_event()`.

**CONFIDENCE**: HIGH

**RATIONALE**: Exhaustive grep confirms exactly one caller. All other audit paths use `emit_event`.
**TYPE**: DORMANT_COMPONENT

---

## FACT 43: `legacy_event_adapter.py` is fully deprecated but still imported at runtime

**EVIDENCE**:
- `backend/app/core/runtime/legacy_event_adapter.py`, lines 1-9: declares itself DEPRECATED with TODO to remove by v0.3.0.
- `backend/app/core/runtime/read_ports.py`, line 16: still imports `from app.core.runtime.legacy_event_adapter import recent_legacy_events`.
- Used in `query_recent_legacy_events()` at read_ports.py:68-73.

**CONFIDENCE**: HIGH

**RATIONALE**: Module self-identifies as DEPRECATED with explicit migration window. Still has one live call path via read_ports.py.
**TYPE**: DORMANT_COMPONENT

---

## FACT 44: `RecallRanker` in `user_profile.py` provides three-factor scoring but is never imported

**EVIDENCE**:
- `backend/app/core/agents/user_profile.py`, lines 93-127: `RecallRanker` computes `total_score = relevance * 0.5 + recency * 0.3 + confidence * 0.2`.
- Line 130: Instantiated as global singleton `recall_ranker = RecallRanker()`.
- No import of `recall_ranker` exists in `memory_engine.py` or `kernel_query_state.py`.
- The main recall path (`kernel.recall_memory()` → `vector_store.search_memories()`) does NOT use `RecallRanker`.

**CONFIDENCE**: MEDIUM

**RATIONALE**: The class exists and is instantiated as a singleton but is never imported by any other module. May be dormant or planned for future use.
**TYPE**: DORMANT_COMPONENT

---

## FACT 45: `query_state` methods duplicate SQL-building patterns from `query_builder.py`

**EVIDENCE**:
- `backend/app/core/runtime/kernel/kernel_query_state.py` manually constructs `WHERE` clauses with ad-hoc `f" WHERE {' AND '.join(clauses)}"` patterns.
- `backend/app/core/runtime/kernel/query_builder.py`, lines 73-81: provides `build_where(clauses)` for the same purpose.
- `query_builder.py` module docstring states its purpose is to centralize WHERE/LIMIT/ORDER construction previously "hand-written across the Kernel mixins."
- The `_query_*` methods in `kernel_query_state.py` still contain hand-written WHERE assembly.

**CONFIDENCE**: MEDIUM

**RATIONALE**: The `query_builder` module was explicitly created to centralize these patterns but is not consistently used.
**TYPE**: DUPLICATION

---

## FACT 46: ApprovalEngine and Kernel._consume_pre_approved duplicate approvals read logic

**EVIDENCE**:
- `backend/app/core/runtime/approval_engine.py`, line 17: calls `kernel.query_state("approvals", id=approval_id)`.
- `backend/app/core/runtime/kernel/kernel.py`, line 567: `_consume_pre_approved()` calls `self.query_state("approvals", id=approval_id)`.
- Both paths serve different consumers (API via ApprovalEngine, internal kernel via direct call) but implementation is identical.

**CONFIDENCE**: MEDIUM

**RATIONALE**: Two read paths with identical implementation but no shared abstraction.
**TYPE**: DUPLICATION

---

## FACT 47: Builtin tools have NO per-tool timeout — only global config

**EVIDENCE**:
- `backend/app/config.py`, line 102: `settings.tool_timeout_seconds` default 30 seconds, applied globally.
- `backend/app/core/harness/mcp_hub.py`, line 703: `invoke_tool()` has NO timeout wrapper for builtin tools.
- `backend/app/core/harness/mcp_mesh.py`, lines 191-194: External MCP tools use `asyncio.wait_for()` with per-server `call_timeout_seconds` — but builtins lack equivalent.

**CONFIDENCE**: HIGH

**RATIONALE**: The `asyncio.wait_for` timeout wrapping is present only for external MCP tools. The builtin tool handler dispatches synchronously without timeout enforcement.
**TYPE**: TOOL_SYSTEM

---

## FACT 48: Tool definitions presented to LLMs use OpenAI function-calling format

**EVIDENCE**:
- `backend/app/core/harness/mcp_hub.py`, lines 679-690:
  ```python
  return [
      {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
      for t in self._tools.values()
  ]
  ```
- Delegated via `kernel.list_capability_definitions()` at `kernel_query_state.py:331-335`.

**CONFIDENCE**: HIGH

**RATIONALE**: The format is explicitly hardcoded in the serialization method.
**TYPE**: TOOL_SYSTEM

---

## Project Structure Summary

| Category | Count | Total Lines |
|----------|-------|-------------|
| Backend Python source files | ~126 | ~23,473 |
| Test Python files | 108 | ~7,500 |
| Total Python files under backend/ | ~234 | ~37,380 |
| Python classes defined (source only) | ~85 | — |
| Python functions defined (source only) | ~280+ | — |
| Markdown docs | 20 | — |
| Builtin tools | 37 across 13 categories | — |
| Registered handlers | 6 (ChatRequested, ApproveRequested, ExecuteRequested, BackgroundTaskRequested, InboxPollRequested, TimerFired) | — |
| Cron schedules | 8 | — |
| Kernel projector modules | 7 (core, aux, background, chat, execution, governance, timer) | — |
| API routes | 16 routers registered in FastAPI app | — |
