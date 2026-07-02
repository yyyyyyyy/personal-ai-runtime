# 数据模型

本文档列出仓库中的全部持久化数据结构。表分类详见 [02-concepts/kernel-boundary.md](../02-concepts/kernel-boundary.md)；本文聚焦具体列与 ChromaDB collections。

## 存储后端

| 后端 | 用途 | 配置 |
|---|---|---|
| SQLite（WAL 模式） | 全部业务表 + 事件日志 + 投影 | `settings.sqlite_path`（默认 `<data_dir>/personal_ai.db`） |
| ChromaDB（PersistentClient） | 记忆与知识的向量索引 | `settings.vector_dir`（默认 `<data_dir>/vectors`） |

`data_dir` 默认 `<repo>/backend/data`，所有相对路径 resolve 到 `BASE_DIR`（[`backend/app/config.py:13-23`](../../backend/app/config.py)）。

SQLite 启用 WAL + `synchronous=NORMAL`（[`backend/app/store/database.py:41-44`](../../backend/app/store/database.py)），线程局部连接缓存。`event_log` 表的两个触发器 `event_log_no_update`/`event_log_no_delete` 对 UPDATE/DELETE 执行 `RAISE(ABORT)` 强制 append-only（[`backend/app/store/schema_ddl.py:220-225`](../../backend/app/store/schema_ddl.py)）。

## 表分类总览

全部 23 张表必须归入 GOVERNED 或 APP_STORAGE（[`backend/app/store/table_registry.py`](../../backend/app/store/table_registry.py)）。

| 类别 | 表数 | 写入权 |
|---|---|---|
| GOVERNED_TABLES | 14 | 仅 Kernel（事件溯源投影） |
| APP_STORAGE_TABLES | 9 | 任意模块直访 |

## GOVERNED 表（事件溯源投影）

预期列契约定义于 [`table_registry.py:64-119`](../../backend/app/store/table_registry.py) 的 `GOVERNED_SCHEMA`。

### `event_log`（真相之源）

```python
frozenset({
    "seq", "id", "type", "aggregate_type", "aggregate_id", "actor", "payload",
    "caused_by", "correlation_id", "ts",
})
```

append-only。索引：`idx_event_log_aggregate`、`idx_event_log_correlation`。

### `goals`

```python
frozenset({
    "id", "title", "description", "status", "progress", "importance", "urgency",
    "deadline", "parent_id", "created_at", "updated_at", "last_activity_at",
})
```

`parent_id` 自引用外键（-goal 树）。

### `actions`

```python
frozenset({
    "id", "goal_id", "title", "status", "executable_plan",
    "created_at", "completed_at",
})
```

### `tasks`

```python
frozenset({
    "id", "name", "description", "parent_goal_id", "parent_task_id", "status",
    "priority", "dependencies_json", "created_at", "updated_at",
})
```

统一任务模型（Goal → Project → Task → Execution）。

### `memories`

```python
frozenset({
    "id", "category", "content", "source", "embedding_id", "created_at",
    "confidence", "derived_from_event", "decayed_at", "status", "origin",
    "claim_status",
})
```

`category` 取值 `{fact, preference, habit, belief, insight, work, personal}`（[`backend/app/api/models.py`](../../backend/app/api/models.py)）。`embedding_id` 在 `emit_event` 中**预计算**，使投影器在同一 SQL 事务写入。`claim_status` 支持 `ratified`/`rejected`/`contested`。

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

`messages.source_event_id` 指向产生该消息的 `event_log` 行（投影溯源守卫验证）。`sources` 列由 `v02_projection_tables` 迁移添加（ALTER TABLE，SQLite 无法原地降级删除）。

### `notifications`

```python
frozenset({
    "id", "type", "title", "content", "read",
    "related_id", "related_type", "notification_type", "created_at",
})
```

`related_id`/`related_type`/`notification_type` 由 `v03_notification_dedup` 迁移添加，配合 `ix_notifications_related_type` 索引使停滞目标的去重查询真正去重。

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
    "fire_at", "status", "created_at", "fired_at",
})
```

### `policy_events` / `grant_events`（治理事件溯源根）

```python
# policy_events
frozenset({"id", "capability", "risk_level", "status", "created_at", "updated_at"})

# grant_events
frozenset({"id", "principal_id", "capability", "status", "created_at", "revoked_at"})
```

## APP_STORAGE 表（可直访）

| 表 | 用途 | 为何不事件溯源 |
|---|---|---|
| `events` | 旧版事件表，已被 `event_log` 取代 | 保留迁移用 |
| `activity_log` | 人类可读活动日志 | event_log 投影派生 |
| `llm_calls` | LLM 调用遥测（延迟、token、成本） | 可从 llm_egress 审计 + 事件流重建 |
| `tool_calls` | 工具调用遥测 | 权威记录是 `CapabilityInvoked`/`CapabilityFailed` 事件 |
| `background_tasks` | 后台任务队列状态 | worker scratch view，生命周期由 `BackgroundTask*` 事件治理 |
| `triggers` | 触发器定义 | 应用配置，用户 UI 自由编辑 |
| `user_profile` | 本地偏好 | 无审计价值，导出 event_log 足够主权 |
| `inbox_emails` | IMAP 原始邮件缓存 | 权威记录是 `InboxEmailRecorded` 事件 |
| `app_settings` | UI 偏好、LLM/Email 连接配置 | 本地运营配置 |

## ChromaDB Collections

`VectorStore`（[`backend/app/store/vector.py`](../../backend/app/store/vector.py)）单例管理两个 collection：

| Collection | 内容 | 写入者 |
|---|---|---|
| `memories` | 记忆向量 | Kernel（`_sync_memory_index`） |
| `knowledge` | 知识库文档块向量 | `knowledge` API（上传时分块向量化） |

方法：`add_memory`/`search_memories`/`search_knowledge`/`add_knowledge_chunk`/`delete_memory`/`delete_knowledge_chunks`。ChromaDB 关闭 telemetry 并 monkey-patch `posthog.capture`（[`vector.py:13-20`](../../backend/app/store/vector.py)）。

## Alembic 迁移

迁移文件在 [`backend/alembic/versions/`](../../backend/alembic/versions/)：

| Revision | down_revision | 内容 |
|---|---|---|
| `initial`（`initial_schema.py`） | — | 基线：一次性创建所有应用表 + kernel 表（含 `event_log` append-only 触发器）+ `projection_checkpoints` + `handler_executions` |
| `v02_projection_tables` | `initial` | 创建 `timer_events`/`policy_events`/`grant_events`；ALTER 加 `messages.sources` 列 |
| `v03_notification_dedup` | `v02_projection_tables` | ALTER 加 `notifications.related_id`/`related_type`/`notification_type`；创建 `ix_notifications_related_type` 索引（参考 `FACT-37`） |

`run_migrations()`（[`backend/app/store/alembic_runner.py`](../../backend/app/store/alembic_runner.py)）用 `backend/alembic.ini`，`command.upgrade(cfg, "head")`，幂等。`env.py` import `app.config.settings` 构造 `sqlite:///{settings.sqlite_path}`，并 `setdefault("LLM_API_KEY", "alembic-migration-key")` 避免 Settings 校验失败。

## Schema 初始化策略

[`backend/app/store/schema_init.py`](../../backend/app/store/schema_init.py) 的 `ensure_schema(db)`（[`schema_init.py:77-94`](../../backend/app/store/schema_init.py)）：

- 若 `db_path == settings.sqlite_path`（生产路径）→ 跑 Alembic migrations（失败回退原始 DDL）。
- 否则（测试/自定义路径）→ 跑 `apply_raw_ddl`（[`schema_init.py:48-74`](../../backend/app/store/schema_init.py)）。

## 一致性验证

| 脚本 | 验证 |
|---|---|
| [`scripts/verify_alembic.py`](../../backend/scripts/verify_alembic.py) | 20 张 `REQUIRED_TABLES` 存在 + `PRAGMA foreign_keys=1` |
| [`scripts/check_projection_provenance.py`](../../backend/scripts/check_projection_provenance.py) | 每条 governed 投影行有对应 `event_log` 事件 |
| [`scripts/verify_vector_consistency.py`](../../backend/scripts/verify_vector_consistency.py) | SQLite memories 集合 = Chroma `memories` collection 集合 |
| [`scripts/verify_export_roundtrip.py`](../../backend/scripts/verify_export_roundtrip.py) | export → import 后 event_log/conversations/messages/goals/memories/notifications 计数一致 |

详见 [05-engineering/testing.md](../05-engineering/testing.md)。
