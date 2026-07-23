# 数据模型

本文档列出仓库中的全部持久化数据结构。表分类详见 [02-concepts/kernel-boundary.md](../02-concepts/kernel-boundary.md)；本文聚焦具体列与 ChromaDB collections。

## 存储后端

| 后端 | 用途 | 配置 |
|---|---|---|
| SQLite（WAL 模式） | 全部业务表 + 事件日志 + 投影 | `settings.sqlite_path`（默认 `<data_dir>/personal_ai.db`） |
| ChromaDB（PersistentClient） | 记忆与知识的向量索引 | `settings.vector_dir`（默认 `<data_dir>/vectors`） |

`data_dir` 默认 `<repo>/backend/data`，所有相对路径 resolve 到 `BASE_DIR`（[`backend/app/config.py`](../../backend/app/config.py)）。

SQLite 启用 WAL + `synchronous=NORMAL`（[`backend/app/store/database.py`](../../backend/app/store/database.py)），线程局部连接缓存。`event_log` 表的两个触发器 `event_log_no_update`/`event_log_no_delete` 对 UPDATE/DELETE 执行 `RAISE(ABORT)` 强制 append-only（[`backend/app/store/schema_ddl.py`](../../backend/app/store/schema_ddl.py)）。

## 表分类总览

全部 20 张表必须归入 GOVERNED 或 APP_STORAGE（[`backend/app/store/table_registry.py`](../../backend/app/store/table_registry.py)）。

| 类别 | 表数 | 写入权 |
|---|---|---|
| GOVERNED_TABLES | 16 | 仅 Kernel（事件溯源投影） |
| APP_STORAGE_TABLES | 4 | 任意模块直访 |

## GOVERNED 表（事件溯源投影）

预期列契约定义于 [`table_registry.py`](../../backend/app/store/table_registry.py) 的 `GOVERNED_SCHEMA`。

### `event_log`（真相之源）

```python
frozenset({
    "seq", "id", "type", "aggregate_type", "aggregate_id", "actor", "payload",
    "caused_by", "correlation_id", "ts",
})
```

append-only。索引：`idx_event_log_aggregate`、`idx_event_log_correlation`。

### `work_items`

```python
frozenset({
    "id", "title", "description", "work_type", "parent_work_id",
    "parent_goal_id", "status", "priority", "dependencies_json",
    "executable_plan", "created_at", "updated_at", "completed_at",
    "progress", "importance", "urgency", "deadline", "last_activity_at",
})
```

`work_type` 区分 `task` / `action` / `background` / `goal`。目标通过 `query_state("work_items", work_type="goal", ...)` 读取（[`kernel_query_state.py`](../../backend/app/core/runtime/kernel/kernel_query_state.py)）。

### `memories`

```python
frozenset({
    "id", "category", "content", "source", "embedding_id", "created_at",
    "confidence", "derived_from_event", "decayed_at", "status", "origin",
    "claim_status", "source_document_id", "source_document_name",
})
```

`category` 取值 `{fact, preference, habit, belief, insight, work, personal}`（[`backend/app/api/models.py`](../../backend/app/api/models.py)）。

### `approvals`

```python
frozenset({
    "id", "task_id", "action", "params", "proposed_by", "status",
    "created_at", "expires_at", "resolved_at", "resolved_by",
})
```

24h TTL，RuntimeLoop 每 ~10s 调 `expire_stale_approvals`。

### `conversations` / `messages`

```python
# conversations
frozenset({"id", "title", "summary", "created_at", "updated_at"})

# messages
frozenset({
    "id", "conversation_id", "role", "content", "tool_calls", "tool_call_id",
    "created_at", "source_event_id", "sources",
})
```

### `notifications`

```python
frozenset({
    "id", "type", "title", "content", "read",
    "related_id", "related_type", "notification_type", "created_at",
})
```

### `inbox_emails`

```python
frozenset({
    "id", "server_id", "sender", "subject", "date", "preview",
    "full_text", "status", "category", "importance", "reason",
    "notified", "digested", "created_at", "received_at",
})
```

由 [`projectors_inbox.py`](../../backend/app/core/runtime/kernel/projectors_inbox.py) 从 `InboxEmailRecorded` 事件投影。

### `projection_checkpoints`

```python
frozenset({"agent_id", "aggregate_type", "last_applied_seq", "snapshot_json", "created_at"})
```

PK 在 `(agent_id, aggregate_type)`。增量重建水位。

### `handler_executions`

```python
frozenset({
    "id", "event_seq", "event_id", "event_type", "handler_name",
    "instance_id", "status", "retry_count", "policy_json",
    "correlation_id", "created_at", "started_at", "completed_at", "error",
})
```

WorkItem 持久化，崩溃恢复源。

### `timer_events`

```python
frozenset({
    "id", "handler_name", "schedule_type", "cron_expr", "delay_seconds",
    "fire_at", "status", "payload_json", "created_at", "fired_at",
})
```

### `policy_events`（治理事件溯源根）

```python
frozenset({"id", "capability", "risk_level", "status", "created_at", "updated_at"})
```

### `tool_calls` / `llm_calls`

Governed 投影，分别由 `CapabilityInvoked/Failed/Denied` 与 `LLMCallRecorded` 事件驱动。

### `user_profile`

```python
frozenset({
    "id", "category", "data_json", "confidence", "created_at", "updated_at",
})
```

由 [`projectors_core.py`](../../backend/app/core/runtime/kernel/projectors_core.py) 从 `UserProfileUpdated` 事件投影。结构化画像类别袋；经 `query_state("user_profile")` / read_ports 读取。

## APP_STORAGE 表（可直访）

| 表 | 用途 | 为何不事件溯源 |
|---|---|---|
| `activity_log` | 人类可读活动日志 | event_log 投影派生 |
| `app_settings` | UI 偏好、LLM/Email 连接配置、以及 knowledge_docs 文档注册表 JSON | 本地运营配置；知识库亦登记为非主权附件（见「非主权附件」章） |
| `memory_index_repairs` | ChromaDB 索引修复队列 | 权威记录是 `MemoryDerived/Updated` 事件；由 RuntimeLoop 重试 |
| `plan_resumes` | 审批暂停后的计划续跑坐标 | 运营续跑态；审批行仍是治理权威；跨进程恢复即可 |

## ChromaDB Collections

`VectorStore`（[`backend/app/store/vector.py`](../../backend/app/store/vector.py)）单例管理两个 collection：

| Collection | 内容 | 写入者 | 主权 |
|---|---|---|---|
| `memories` | 记忆向量 | Kernel（`_sync_memory_index`） | State 派生（INV-S3） |
| `knowledge` | 知识库文档块向量 | `product/knowledge.py`（上传时分块） | 非主权附件（Path B） |

## 非主权附件

登记于 [`table_registry.py`](../../backend/app/store/table_registry.py) 的 `NON_SOVEREIGN_ATTACHMENTS`。**不能**仅靠 `event_log` 重建；不得当作第二真相源（INV-S4）。

当前登记：`knowledge`（`app_settings` 中 category=`knowledge_docs` + Chroma collection `knowledge`）。写路径在 `product/knowledge.py`；`AppConfigChanged` 仅审计。

## Schema 初始化

初始 Schema 定义在 [`backend/alembic/versions/`](../../backend/alembic/versions/)：

| Revision | down_revision | 内容 |
|---|---|---|
| `0001_consolidated` | — | 单一初始 schema：全部应用表 + kernel 表 + 投影表 + append-only 触发器 |

`alembic upgrade head` 一次应用完整 schema。

`run_migrations()`（[`backend/app/store/alembic_runner.py`](../../backend/app/store/alembic_runner.py)）用 `backend/alembic.ini`，`command.upgrade(cfg, "head")`，幂等。

## Schema 初始化策略

[`backend/app/store/schema_init.py`](../../backend/app/store/schema_init.py) 的 `ensure_schema(db)`：

- 若 `db_path == settings.sqlite_path`（生产路径）→ 应用 Alembic schema（失败回退 raw DDL）。
- 否则（测试/自定义路径）→ 跑 `apply_raw_ddl`。

## 一致性验证

| 脚本 | 验证 |
|---|---|
| [`scripts/verify_alembic.py`](../../backend/scripts/verify_alembic.py) | 19 张必需表存在 + `PRAGMA foreign_keys=1` |
| [`scripts/check_projection_provenance.py`](../../backend/scripts/check_projection_provenance.py) | 每条 governed 投影行有对应 `event_log` 事件 |
| [`scripts/verify_vector_consistency.py`](../../backend/scripts/verify_vector_consistency.py) | SQLite memories 集合 = Chroma `memories` collection 集合 |
| [`scripts/verify_export_roundtrip.py`](../../backend/scripts/verify_export_roundtrip.py) | export → import 后 event_log/conversations/messages/work_items/memories/notifications 计数一致 |

详见 [05-engineering/testing.md](../05-engineering/testing.md)。
