# 后端 API 层

本文档描述后端 HTTP API 层。完整端点签名表见 [06-reference/api-endpoints.md](../06-reference/api-endpoints.md)；本文聚焦结构与流程。

## 应用入口

[`backend/app/main.py`](../../backend/app/main.py) 是 FastAPI 入口：`FastAPI(title="Personal AI Runtime", version=VERSION, lifespan=lifespan)`（[`main.py:333-354`](../../backend/app/main.py)）。

### 路由挂载

16 个 router 在 [`main.py:372-387`](../../backend/app/main.py) 挂载：

```
chat, dashboard, system, settings_api, memory, goals, notifications,
tasks, telemetry_api, approvals, background_tasks, triggers, inbox,
connectors, timeline, knowledge
```

> `backend/app/api/workflows.py` 定义了完整 router，但 `main.py` **未 include_router**。该 router 在当前运行实例中不可达。代码库中证据不足：未见注释或 git 记录解释原因。

### 中间件（外到内）

1. **`RequestIDMiddleware`**（[`main.py:193-231`](../../backend/app/main.py)）— 读取或生成 `X-Request-ID`（uuid4 前 16 位），存入 `request_id_var` ContextVar，响应头回写。
2. **`CORSMiddleware`**（[`main.py:358-365`](../../backend/app/main.py)）— `allow_origins=settings.cors_origins.split(",")`、`allow_credentials=True`、方法 `GET/POST/PUT/PATCH/DELETE/OPTIONS`、头 `Authorization/Content-Type/X-Request-ID`。
3. **`AuthMiddleware`**（[`main.py:110-190`](../../backend/app/main.py)）— 纯 ASGI Bearer Token 中间件（刻意避开 `BaseHTTPMiddleware` 以免缓冲 SSE）。详见 [05-engineering/security.md](../05-engineering/security.md)。

## 生命周期

`lifespan(app)`（[`main.py:237-328`](../../backend/app/main.py)）：

**Startup**：

1. `run_startup_checks()` → 快照
2. AUTH_TOKEN 安全策略：未设且非 localhost bind 且未开 `ALLOW_NO_AUTH_ON_EXPOSED` → `sys.exit(1)`
3. `init_scheduler()` — 注册 cron + 任务依赖订阅
4. `capability_governance.seed_from_json(kernel)` — 从 [`capability_policy.json`](../../backend/capability_policy.json) 播种 `PolicyCreated`
5. `await runtime_loop.start()` — 统一循环
6. `trigger_engine.seed_builtin_triggers()`
7. `await start_mcp_mesh()` — 连接 stdio MCP servers
8. `enrich_with_mcp_status(...)`
9. 若裸奔运行，启动 600s 周期安全告警协程

**Shutdown**：

1. `await stop_mcp_mesh()`
2. 取消周期性 auth warning
3. `await runtime_loop.stop()`
4. 关闭所有 WebSocket

## 端点分类速览

按职责分组（详见 [06-reference/api-endpoints.md](../06-reference/api-endpoints.md)）：

| Router | prefix | 关键端点 | 副作用类型 |
|---|---|---|---|
| chat | `/api/chat` | 会话 CRUD、`POST /conversations/{id}/messages`（**SSE**）、`POST /chat/approvals/{id}/resolve` | Kernel 事件 + LLM + 工具执行 |
| memory | `/api/memory` | memories CRUD、search、ratify/reject/contest、portrait、graph | Kernel 事件 + Chroma |
| goals | `/api/goals` | goal CRUD、actions、`/{id}/decompose`（LLM） | Kernel 事件 + LLM |
| tasks | `/api/tasks` | task CRUD、status、dependencies | Kernel 事件 |
| background_tasks | `/api/tasks/background` | 后台任务 | Kernel 事件 |
| approvals | `/api/approvals` | 列表、`/{id}/approve`、`/{id}/reject` | `submit_command("ApproveRequested")` + 工具执行 |
| inbox | `/api/inbox` | 列表、`/poll`（IMAP）、`/digest`、状态更新 | 网络出口 + Kernel 事件 |
| triggers | `/api/triggers` | CRUD、`/evaluate` | Kernel 事件 |
| notifications | `/api/notifications` | 列表、`/{id}/read`、`/read-all` | Kernel 事件 |
| dashboard | `/api/dashboard` | `GET /` | **只用 Kernel ABI**（一致性测试床） |
| system | `/api/system` | health/live/ready/info/mcp-status、export/import/encrypted、`DELETE /data` | 数据主权（含破坏性） |
| settings_api | `/api/settings` | llm GET/PUT/test、email GET/PUT/test、prompt GET/PUT、notifications | DB 写 + 网络出口 + 文件写 |
| telemetry_api | `/api/telemetry` | cost/summary/by-model、llm-calls、tool-calls、tool-summary、memory/stats、health | 只读 |
| timeline | `/api/timeline` | `/events`（分页 + 中文标签） | 只读 event_log |
| knowledge | `/api/knowledge` | upload、documents、search、delete | 文件 + Chroma + app_settings |
| connectors | `/api/connectors` | 列表、详情、test、registry、install、uninstall | 可能进程间/网络 + 文件写 |

## SSE 流式端点

**唯一 SSE 端点**：`POST /api/chat/conversations/{conv_id}/messages`（[`chat.py:83-188`](../../backend/app/api/chat.py)），`text/event-stream`。

事件类型：`text_delta`、`tool_call_start`、`tool_result`、`sources`、`confirmation_required`、`done`、`error`、`ping`（15s 心跳）。

实现细节（[`chat.py:122-178`](../../backend/app/api/chat.py)）：

- 内部生成 `correlation_id = "chat_" + uuid[:12]`，从 `sse_queue_registry` 注册内存队列。
- 上限 `settings.total_tool_loop_timeout + 10s`；超时返回 `error`。
- 既监听 SSE 队列，也回退查询 `event_log` 中的 `ChatDone`/`ChatCompleted`。
- 响应头：`Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no`（禁用 nginx 缓冲）。

`AuthMiddleware` 刻意设计为纯 ASGI 中间件以避免 `BaseHTTPMiddleware` 缓冲整段响应体。

## WebSocket 端点

`WS /ws`（[`main.py:404-429`](../../backend/app/main.py)）— 实时通知推送。

- 鉴权：`Sec-WebSocket-Protocol: auth.<token>` 子协议（[`main.py:101-107`](../../backend/app/main.py)），失败关闭码 4401，成功回 `auth.ok`。
- 行为：维持连接列表，接收客户端 `ping` 回 `pong`。
- `broadcast_notification(event)`（[`main.py:432-455`](../../backend/app/main.py)）向所有连接广播 JSON，自动清理已断开连接。

无其他 WebSocket 端点。

## 数据访问层

### `backend/app/store/`

| 文件 | 职责 |
|---|---|
| [`database.py`](../../backend/app/store/database.py) | `Database` 单例，SQLite + WAL + `synchronous=NORMAL`；线程局部连接缓存；`get_db()` contextmanager 自动 commit/rollback；只读便捷方法 `get_conversation`/`list_conversations`/`get_message`/`get_recent_messages`；`wal_checkpoint`；`log_activity` |
| [`schema_init.py`](../../backend/app/store/schema_init.py) | `ensure_schema(db)`：生产路径跑 Alembic，测试/自定义路径跑原始 DDL |
| [`alembic_runner.py`](../../backend/app/store/alembic_runner.py) | `run_migrations()` 用 `backend/alembic.ini`，`command.upgrade(cfg, "head")`，幂等 |
| [`schema_ddl.py`](../../backend/app/store/schema_ddl.py) | 完整 DDL。`APP_STORAGE_DDL`（17 张应用表）+ Kernel space DDL（`event_log` + append-only 触发器、`projection_checkpoints`、`handler_executions`、`timer_events`、`policy_events`、`grant_events`） |
| [`table_registry.py`](../../backend/app/store/table_registry.py) | 表分类（GOVERNED vs APP_STORAGE）+ `GOVERNED_SCHEMA` 契约。详见 [02-concepts/kernel-boundary.md](../02-concepts/kernel-boundary.md) |
| [`vector.py`](../../backend/app/store/vector.py) | `VectorStore` 单例，ChromaDB `PersistentClient(path=settings.vector_dir)`，关闭 telemetry 并 monkey-patch `posthog.capture`。两个 collection：`memories`、`knowledge` |

## Product 层

[`backend/app/product/`](../../backend/app/product/)：

| 文件 | 模块 | 职责 |
|---|---|---|
| [`inbox.py`](../../backend/app/product/inbox.py) | `poll_inbox`/`generate_inbox_digest`/`list_inbox_emails`/`mark_inbox_email_status`/`latest_digest`/`apply_inbox_poll_payload` | 邮件应用层：经 `kernel.invoke_capability("check_inbox")` 或 `submit_command("InboxPollRequested")` 拉邮件；LLM 分类；同步已读；写 `inbox_emails`；emit `InboxEmailRecorded`；为 important 邮件推通知；每日摘要幂等 |
| [`notifications.py`](../../backend/app/product/notifications.py) | `create_notification`/`find_notification`/`parse_related_id` | 经 Kernel event log 写；按 `(type, title)` 幂等；支持 `related_id` 嵌入前缀 |
| [`digital_legacy.py`](../../backend/app/product/digital_legacy.py) | `DigitalLegacy` 类 + `digital_legacy` 单例 | 数据主权：`export_all`/`import_all(read_only)`/`destroy_all`（删 SQLite + vector 目录并重建）；`_import_legacy_goals_memories` 兼容旧版；`export_to_file`/`import_from_file`/`snapshot_counts` |
| [`encrypted_sync.py`](../../backend/app/product/encrypted_sync.py) | `encrypt_snapshot`/`decrypt_snapshot` + `EncryptedSyncError` | AES-GCM + PBKDF2-HMAC-SHA256（600k 迭代）；blob 布局 `[16B salt][12B nonce][ciphertext + 16B tag]` base64；`BLOB_FORMAT = "encrypted_snapshot_v1"`；最小密码 8 字符 |
| [`personal_dashboard.py`](../../backend/app/product/personal_dashboard.py) | `generate_dashboard` + 5 个 `_widget_*` | 一致性测试床：每个 widget 仅用 Kernel ABI（`query_state`/`read_events`/`recall_memory`），零 SQL、零文件、零 ChromaDB 直访 |

## 直接访问 DB 的端点

绝大多数 router 通过 Kernel ABI。例外（直访 `db.get_db()` 或文件，但都在 APP_STORAGE 范围）：

- [`knowledge.py`](../../backend/app/api/knowledge.py) — 文件 + ChromaDB + `app_settings`
- `workflows.py`（未挂载）
- [`connectors.py`](../../backend/app/api/connectors.py) 的 install/uninstall — 写 [`mcp_config.json`](../../backend/mcp_config.json)
- [`inbox.py`](../../backend/app/api/inbox.py) 内部 `product/inbox.py` — 直访 `inbox_emails`（APP_STORAGE）

## 请求/响应模型

所有 Pydantic 模型定义于 [`backend/app/api/models.py`](../../backend/app/api/models.py)（如 `SendMessageRequest`、`ResolveApprovalRequest`、`CreateGoalRequest`、`CreateMemoryRequest`、`UpdateMemoryRequest`（category 必须在 `{fact, preference, habit, belief, insight, work, personal}`）、`CreateTaskRequest`、`UpdateTaskStatusRequest`、`CreateBackgroundTaskRequest`、`CreateTriggerRequest`、`ExportRequest`/`ImportRequest`/`EncryptedExportRequest`/`EncryptedImportRequest`、`UpdateInboxStatusRequest`、`LlmProviderInput`/`UpdateLlmConfigRequest`/`UpdateEmailConfigRequest`/`TestEmailRequest`/`TestLlmRequest`/`PromptConfig`/`NotificationSettings`、`InstallConnectorRequest`）。

确认码常量（[`system.py:31-33`](../../backend/app/api/system.py)）：`EXPORT_CONFIRM="EXPORT_ALL_DATA"`、`DESTROY_CONFIRM="DESTROY_ALL_DATA"`、`IMPORT_CONFIRM="DESTROY_AND_IMPORT"`。
