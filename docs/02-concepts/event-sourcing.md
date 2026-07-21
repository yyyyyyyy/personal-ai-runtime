# 事件溯源

本文档解释 Personal AI Runtime 的事件溯源模型：不可变 `event_log` 是真相之源，所有业务状态都是其投影。

## 真相层：`event_log`

`event_log` 是一张 append-only 的 SQLite 表，由 SQLite 触发器强制不可变（[`backend/app/store/schema_ddl.py`](../../backend/app/store/schema_ddl.py) 的 `event_log_no_update` / `event_log_no_delete`，对 UPDATE/DELETE 执行 `RAISE(ABORT)`）。

事件结构由不可变 dataclass `Event` 定义（[`backend/app/core/runtime/kernel/event.py`](../../backend/app/core/runtime/kernel/event.py)）：

| 字段 | 含义 |
|---|---|
| `seq` | 日志分配的递增序号（主键之一） |
| `id` | 事件 UUID |
| `type` | 事件类型字符串（如 `WorkItemCreated`、`MessageAppended`），常量集中定义于 [`kernel/constants.py`](../../backend/app/core/runtime/kernel/constants.py) |
| `aggregate_type` | 聚合根类型（`work_item`、`conversation`、`memory`、`execution` 等） |
| `aggregate_id` | 聚合实例 id |
| `actor` | 触发者（`user`、`system`、`agent:{instance_id}`、`scheduler`、`connector:*` 等） |
| `payload` | JSON 业务数据 |
| `caused_by` | 一跳因果前驱事件 id |
| `correlation_id` | 跨事件链的关联 id（如一次聊天回合） |
| `ts` | 时间戳 |

## Kernel 写入路径

唯一的写入入口是 `Kernel.emit_event()`（[`backend/app/core/runtime/kernel/kernel.py`](../../backend/app/core/runtime/kernel/kernel.py)）。它在单个 SQLite 事务内完成四件事：

```mermaid
flowchart LR
    A["emit_event(type, aggregate_type,<br/>aggregate_id, payload, actor,<br/>caused_by, correlation_id)"]
    A --> B["1. INSERT into event_log<br/>(immutable)"]
    B --> C["2. projectors.apply(event, conn)<br/>同步投影到 governed 表"]
    C --> D["3. _sync_memory_index(event)<br/>ChromaDB 索引同步"]
    D --> E["4. _dispatch(event)"]
    E --> F["sync subscribers"]
    E --> G["async dispatcher<br/>(Scheduler) fire-and-forget"]
    E --> H["resolve submit_command futures"]
```

关键不变量：投影与触发事件在同一事务内完成，因此投影状态始终与其原因一致。ChromaDB 同步发生在事务提交后；若失败，事件被加入 `_pending_memory_index_repairs`（上限 1000），由 [`scripts/verify_vector_consistency.py`](../../backend/scripts/verify_vector_consistency.py) 对账修复。

## 同步命令包装：`submit_command`

`Kernel.submit_command(...)`（[`kernel.py`](../../backend/app/core/runtime/kernel/kernel.py)）是 `emit_event` 的同步包装：发出请求事件后，await 一个由 `(correlation_id, completion_type)` 匹配的完成事件。默认完成类型把 `Requested` 替换为 `Completed`。HTTP API 的多数写操作（如 `POST /api/chat/approvals/{id}/resolve`、`POST /api/work-items/{id}/decompose`）走这条路。

## 读路径

Kernel 提供两类读 API：

- **拉取式** `read_events(...)`（[`kernel.py`](../../backend/app/core/runtime/kernel/kernel.py)）— 支持按类型、聚合、时间、actor 等过滤的事件日志读取。
- **订阅式** `subscribe_events(handler, type, aggregate_type)`（[`kernel.py`](../../backend/app/core/runtime/kernel/kernel.py)）— 注册回调，返回反订阅函数。
- **状态查询** `query_state(selector, **filters)`（[`kernel_query_state.py`](../../backend/app/core/runtime/kernel/kernel_query_state.py)）— 从投影表读取当前状态。支持的选择器：`work_items`、`approvals`、`memories`、`notifications`、`policy_events`、`messages`、`conversations`、`inbox_emails`、`tool_calls`、`llm_calls`（timer/background/user_profile 经 `read_ports` → `query_builder`）。

## 投影器

投影器把不可变事件转换为可变状态（物化视图）。注册通过装饰器：

```python
@projector("WorkItemCreated")
def project_work_item_created(event, conn):
    ...
```

实现于 [`backend/app/core/runtime/kernel/projectors_registry.py`](../../backend/app/core/runtime/kernel/projectors_registry.py)。按聚合拆分为多个文件：

| 文件 | 投影内容 |
|---|---|
| `projectors_core.py` | work_items（含 goal/task/action）、memories（含 `embedding_id` 回填）、approvals、notifications、claims、user_profile |
| `projectors_chat.py` | conversations / messages |
| `projectors_execution.py` | `handler_executions` + `background_tasks` |
| `projectors_governance.py` | `policy_events` + tool_calls / llm_calls |
| `projectors_inbox.py` | inbox_emails + timer_events |

新增投影器须同时在 `projectors_registry._OWNED_TABLES` 注册所属表，`kernel.rebuild()` 才能正确清空并重建。

## 可重建性

State 是 Event Log 的纯投影，可随时清空并从日志重放重建。Kernel 提供：

- `rebuild(aggregate_type)` — 增量重建：从 `projection_checkpoints.last_applied_seq` 续放（[`scripts/verify_snapshot_rebuild.py`](../../backend/scripts/verify_snapshot_rebuild.py) 验证）。
- `rebuild_all()` — 全量重建：清空所有 governed 表后从 seq=0 重放（[`scripts/verify_rebuild.py`](../../backend/scripts/verify_rebuild.py) 验证，快照前后字节比对）。
- `save_projection_snapshots()` — 把投影序列化为快照。

## 因果链与关联

- `caused_by` 指向**直接前驱**事件 id，形成一跳因果链。
- `correlation_id` 贯穿一次逻辑操作的全部事件（如一次聊天回合的所有 `ChatRequested` → `CapabilityInvoked` → `ChatCompleted`）。

## 与传统事件溯源的差异

代码中可观察到的简化：

- **同步投影**：投影在 `emit_event` 事务内同步完成，而非异步 fan-out。优势是一致性；代价是 emit 延迟包含投影开销。
- **异步派发器在事件日志之上**：Scheduler 通过 `kernel.set_async_dispatcher()`（[`kernel.py`](../../backend/app/core/runtime/kernel/kernel.py)）注册一个 fire-and-forget 派发器，在 `emit_event` 提交后把每个事件投递给 [`agent_scheduler.py`](../../backend/app/core/runtime/agent_scheduler.py) 的 `_dispatch_to_scheduler`，后者按 [`handler_registry.get_handler(event.type)`](../../backend/app/core/runtime/handler_registry.py) 路由——匹配则 `enqueue` 一个 WorkItem 给 Scheduler 执行，不匹配则跳过。这不是独立消息代理，event_log 才是唯一真相。
- **混合存储**：并非所有表都是 governed 投影。`activity_log`、`app_settings`、`memory_index_repairs` 是 APP_STORAGE，可直访（见 [kernel-boundary.md](kernel-boundary.md)）。`background_tasks` / `user_profile` 为 GOVERNED 事件投影。

## 相关验证脚本

| 脚本 | 验证内容 |
|---|---|
| [`scripts/verify_rebuild.py`](../../backend/scripts/verify_rebuild.py) | 全量重建后投影状态字节一致 |
| [`scripts/verify_snapshot_rebuild.py`](../../backend/scripts/verify_snapshot_rebuild.py) | 增量重建 + checkpoint 不回退 |
| [`scripts/verify_conversation_rebuild.py`](../../backend/scripts/verify_conversation_rebuild.py) | 对话消息可重建且 `source_event_id` 可溯源 |
| [`scripts/verify_goal_rebuild.py`](../../backend/scripts/verify_goal_rebuild.py) | work_items(goal) 的 `parent_goal_id`/`progress` 重建后保留 |
| [`scripts/verify_memory_lifecycle.py`](../../backend/scripts/verify_memory_lifecycle.py) | 记忆 Derived/Updated/Deleted 全生命周期可重建 |
| [`scripts/verify_export_roundtrip.py`](../../backend/scripts/verify_export_roundtrip.py) | export → import 数据无损 |

详见 [05-engineering/testing.md](../05-engineering/testing.md)。
