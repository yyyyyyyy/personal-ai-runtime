# Execution Model（三车道）

Personal AI Runtime 的所有执行路径用**一套三车道语义**解释。不要再引入平行的「Agent 调度 / 旁路 RPC / 特殊循环」叙事。

## 定义

| Lane | 名称 | 是什么 | 入口 | 持久化 |
|------|------|--------|------|--------|
| **A** | Scheduled Work | 一次 Handler 调用（`ScheduledExecution`） | `emit_event` → Scheduler fan-out | `handler_executions` + Execution* 事件 |
| **B** | Sync Capability | 受治理的外部效果 | `Kernel.invoke_capability` | Capability* 事件（不经 Scheduler） |
| **C** | Maintenance | 时钟驱动的组合动作 | `RuntimeLoop` / `@reaction` | 仅当其 emit / invoke 时进入 A 或 B |

## 概念对照

| 说法 | 含义 |
|------|------|
| 一次 **ScheduledExecution** | Lane A：一个 handler × 一个触发事件 |
| 一次 **Work（领域）** | `work_items` 投影行（goal / task / action）——与 Lane A 不同名不同表 |
| 一次 **Capability Invocation** | Lane B：门控 + `mcp_hub.invoke_tool` + 审计事件 |
| Runtime 调度 | Lane A Scheduler + Lane C RuntimeLoop |
| 同步调用 | Lane B（及 `submit_command` 对完成事件的 Future 等待） |
| 异步执行 | Lane A（async dispatcher → ScheduledExecution） |

## 不变量

1. **一事件可扇出 N 个 Lane A 执行**：`HandlerRegistry` 对同一 `event.type` 保留 handler 列表；Scheduler 为每个 handler 建一个 `ScheduledExecution`。
2. **Lane B 不是 WORK**：工具循环需要同步返回值；CAPABILITY 与 WORK 是不同原语（见 [runtime-algebra.md](runtime-algebra.md)）。
3. **Lane C 不是新原语**：Reaction / timer maintenance 是 `subscribe + emit/invoke` 的组合。
4. **GOVERNED 状态只经投影写入**：包括审批过期（emit `ApprovalDenied` + projector）。
5. **流式输出走 TRANSPORT**：Lane A/B 执行过程中的 `text_delta` 等瞬时信号经 Transport 推送，不进入 `event_log`（见 [runtime-algebra.md §1.6](runtime-algebra.md)）。

## 控制面原语（Control Plane）

单进程 asyncio 控制面（**非目标**：分布式 lease / 多 worker）。强度与测试锚点：

| Primitive | Status | Evidence / guard |
|-----------|--------|------------------|
| Retry | Present | Lane A `_maybe_retry` + ExecutionRetried；`test_scheduler*` / policy |
| Cancellation (mid-flight) | Present (durable) | `Scheduler.request_cancel` → ExecutionFailed before `task.cancel`；BG via WorkItemStatusChanged；`test_background_control_plane` |
| Recovery | Present | `recover_scheduled_executions` + BG running→pending；scheduler/runtime_loop tests |
| Lease / multi-worker ownership | Absent / **Non-goal** | 单进程；见 [runtime-invariants.md](runtime-invariants.md) INV-W6；`check_single_process_control_plane.py` |
| Quota | Partial | HTTP/WS rate limits；tool-loop token/iteration caps；无 per-tenant scheduler quota |
| Backpressure | Present | `scheduler_max_pending` → `queue_full` |
| Durable continuation | Partial | `plan_resumes` for Execute/Approve；**Chat Brain 工具环跨进程不续跑**（审批后 one-shot `continue_after_tool_result`，见 ADR-R011） |

## 负空间登记（Negative Space）

| Missing primitive | Status | Notes |
|-------------------|--------|-------|
| Distributed lease | Non-goal | Personal single-process Runtime |
| Multi-worker Scheduler | Non-goal | Same process as FastAPI lifespan |
| Chat tool-loop cursor across restart | Absent (product: C2) | Resolve runs approved tool + one-shot text；不重开完整 tool loop |
| Multi-tenant isolation | Non-goal | Single-user Principal model |

## 生命周期对照（Work / Execution / PlanResume）

| Concept | Create | Start | End | Retry | Recover | Destroy/GC |
|---------|--------|-------|-----|-------|---------|------------|
| **ScheduledExecution** | ExecutionRequested | ExecutionStarted | Completed/Failed | ExecutionRetried (Lane A) | running→retrying→pending | Soft-prune terminal rows (`handler_executions_retention_days`) |
| **WorkItem** | WorkItemCreated | StatusChanged(running) | completed/cancelled | Domain `retrying` **API-allowed but not operationally emitted** (Lane A owns retry) | BG running→pending | Domain delete events |
| **PlanResume** | register on pending approval | — | take on approve/deny | — | SQLite durable | clear on cancel/deny/expire |
| **Chat tool loop** | ChatRequested | Brain.chat_stream | ChatCompleted / confirmation_required | — | **Not durable** (ADR-R011) | — |

Domain `TaskStatus.RETRYING` remains in the FSM for API compatibility；钉死测试：生产路径不赋值该状态。
