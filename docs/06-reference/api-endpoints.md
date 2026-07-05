# API 端点参考

全端点签名表。认证说明：所有端点（除标 `public`）在 `AUTH_TOKEN` 配置时经全局 `AuthMiddleware` Bearer 校验；**没有任何端点用 FastAPI Depends 式 AUTH_TOKEN 依赖**。

跳过认证路径（`SKIP_AUTH_PATHS`，[`main.py`](../../backend/app/main.py)）：`/`、`/api/system/health`、`/api/system/live`、`/docs`、`/redoc`、`/openapi.json`。

## chat — `/api/chat`（[`api/chat.py`](../../backend/app/api/chat.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| POST | `/api/conversations` | `19-23` | query `title: str\|None` | conversation dict | DB 写 conversations |
| GET | `/api/conversations` | `26-29` | query `limit=50` | list[conversation] | 无 |
| GET | `/api/conversations/{conv_id}` | `32-38` | path | conversation / 404 | 无 |
| DELETE | `/api/conversations/{conv_id}` | `41-48` | path | `{"status":"ok"}` / 404 | 删 conversation + messages |
| PATCH | `/api/conversations/{conv_id}` | `51-58` | path, query `title` | `{"status":"ok"}` / 404 | 更新 title |
| GET | `/api/conversations/{conv_id}/messages` | `61-80` | path, query `limit=100` | list[message]（assistant content 经 `strip_tool_markup`，sources 解析 JSON） | 无 |
| POST | `/api/conversations/{conv_id}/messages` | `83-188` | body `SendMessageRequest{content: str}` | **SSE 流**：`text_delta`/`tool_call_start`/`tool_result`/`sources`/`confirmation_required`/`done`/`error`/`ping`（15s 心跳） | emit `ChatRequested` → Brain LLM + 工具执行 + 可能 approval |
| POST | `/api/chat/approvals/{approval_id}/resolve` | `235-271` | body `ResolveApprovalRequest{decision, tool_name, tool_args, conv_id, tool_call_id}` | `{status, result, assistant_message?}` | `submit_command("ApproveRequested")` + 工具执行 + 可能续接 LLM |

## memory — `/api/memory`（[`api/memory.py`](../../backend/app/api/memory.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| GET | `/memories` | `19-22` | query `category`, `limit=50` | list | 无 |
| GET | `/memories/grouped` | `25-29` | query `limit=100` | `{"memories":[...]}` | 无 |
| POST | `/memories` | `32-42` | `CreateMemoryRequest{content, category?}`（category ∈ `{fact,preference,habit,belief,insight,work,personal}`） | `{"id","status":"ok"}` | SQLite + ChromaDB |
| GET | `/memories/search` | `45-50` | query `q`, `n=5` | results | 读 ChromaDB |
| DELETE | `/memories/{memory_id}` | `53-59` | path | `{"status":"ok"}` / 404 | 删 SQLite + ChromaDB |
| PUT | `/memories/{memory_id}` | `62-75` | `UpdateMemoryRequest{content?, category?}` | `{"status":"ok"}` / 404 | 更新 |
| POST | `/memories/{memory_id}/ratify` | `80-95` | path | `{"status":"ok","claim_status":"ratified"}` / 404 / 400 | emit `ClaimRatified` |
| POST | `/memories/{memory_id}/reject` | `98-113` | path | 同上 `rejected` | emit `ClaimRejected` |
| POST | `/memories/{memory_id}/contest` | `116-131` | path | 同上 `contested` | emit `ClaimContested` |
| GET | `/portrait` | `136-192` | — | `{profile, habits, goals}` | 无 |
| GET | `/graph` | `202-272` | query `limit=50` | `{nodes, edges}` | 无 |

## goals — `/api/goals`（[`api/goals.py`](../../backend/app/api/goals.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| POST | `/` | `44-77` | `CreateGoalRequest{title, description="", importance=0.5, urgency=0.5, parent_id?, deadline?}` | goal dict | emit `GoalCreated` |
| GET | `/` | `80-86` | query `status?`, `limit=50` | list | 无 |
| GET | `/{goal_id}` | `89-98` | path | goal + actions + events | 无 |
| PUT/PATCH | `/{goal_id}` | `101-137` | body dict（title/description/status/progress/importance/urgency/deadline/parent_id） | goal dict / 404 | emit `GoalUpdated` 或 `GoalCompleted` |
| DELETE | `/{goal_id}` | `140-159` | path | `{"status":"ok"}` / 404 | 每 action emit `ActionDeleted`，再 emit `GoalDeleted` |
| POST | `/{goal_id}/actions` | `164-193` | `CreateActionRequest{title, goal_id=""}` | action dict | emit `ActionCreated` + `GoalTouched` |
| PUT | `/{goal_id}/actions/{action_id}` | `196-230` | body dict（status, title） | `{"status":"ok"}` / 404 | emit `ActionUpdated` + `GoalTouched`；completed 时联动 progress + 通知 + memory |
| DELETE | `/{goal_id}/actions/{action_id}` | `233-247` | path | `{"status":"ok"}` / 404 | emit `ActionDeleted` |
| POST | `/{goal_id}/decompose` | `257-338` | path | `{"steps": list[str]}` | **LLM 调用**：拆解目标 3-10 步 |

## tasks — `/api/tasks`（[`api/tasks.py`](../../backend/app/api/tasks.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| POST | `/` | `12-26` | `CreateTaskRequest{name="", title="", description="", goal_id="", parent_goal_id?, parent_task_id?, priority=0, dependencies?}` | task dict | task_engine 创建 |
| GET | `/` | `29-31` | query `status?`, `limit=50` | list | 无 |
| GET | `/{task_id}` | `34-39` | path | task / 404 | 无 |
| GET | `/{task_id}/subtasks` | `42-46` | path | list / 404 | 无 |
| DELETE | `/{task_id}` | `49-61` | path | `{"status":"ok"}` / 404 | emit `TaskDeleted` |
| GET | `/goals/{goal_id}/tree` | `64-68` | path | tree / 404 | 无 |
| PATCH | `/{task_id}/status` | `80-93` | `UpdateTaskStatusRequest{status, result=""}`（别名映射 in_progress→running 等） | task / 404 / 400 | task_engine 更新 |
| GET | `/{task_id}/dependencies-met` | `96-101` | path | `{"met": bool}` / 404 | 无 |

## background_tasks — `/api/tasks/background`（[`api/background_tasks.py`](../../backend/app/api/background_tasks.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| POST | `/` | `11-19` | `CreateBackgroundTaskRequest{user_request, plan?}` | task dict / 400 | background_worker 创建 |
| GET | `/` | `22-24` | query `limit=50` | list | 无 |
| GET | `/{task_id}` | `27-32` | path | task / 404 | 无 |

## approvals — `/api/approvals`（[`api/approvals.py`](../../backend/app/api/approvals.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| GET | `/` | `13-26` | query `limit=50`, `pending_only=False`, `enriched=False` | list（enriched 含 `flow_type`/`flow_label`/`correlation_id`） | 无 |
| GET | `/{approval_id}` | `29-35` | path | approval / 404 | 无 |
| POST | `/{approval_id}/approve` | `38-107` | path | `{status, result}` / 404 / 400 / 504 | `submit_command("ApproveRequested", decision="approve")` + 工具执行 |
| POST | `/{approval_id}/reject` | `110-145` | query `reason=""` | `{status}` / 404 / 400 / 504 | `submit_command("ApproveRequested", decision="deny")` |

## inbox — `/api/inbox`（[`api/inbox.py`](../../backend/app/api/inbox.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| GET | `/` | `21-29` | query `category?`(important/actionable/ignorable), `limit=50`, `status="pending"` | list | 无 |
| GET | `/digest` | `32-35` | — | digest / `{"message":"no digest yet"}` | 无 |
| POST | `/poll` | `38-40` | query `limit=20` | poll result | **网络出口**：IMAP 拉邮件 + LLM 分类 + SQLite 写 + 通知 |
| POST | `/digest` | `43-46` | — | digest / `{"message":"no emails to digest"}` | 生成每日摘要（幂等）+ 通知 |
| PATCH | `/{email_id}/status` | `49-57` | `UpdateInboxStatusRequest{status: pending\|read\|handled}` | `{id, status}` / 404 / 400 | SQLite 更新 |

## triggers — `/api/triggers`（[`api/triggers.py`](../../backend/app/api/triggers.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| POST | `/` | `11-22` | `CreateTriggerRequest{name, trigger_type="", condition={}, action_type="suggestion", action_config?}` | trigger dict / 400 | trigger_engine 创建 |
| GET | `/` | `25-27` | — | list | 无 |
| DELETE | `/{trigger_id}` | `30-36` | path | `{"status":"ok"}` / 404 | 删除 |
| POST | `/evaluate` | `39-42` | — | `{"suggestions":[...]}` | `trigger_engine.evaluate_all()` |

## notifications — `/api/notifications`（[`api/notifications.py`](../../backend/app/api/notifications.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| GET | `/` | `15-23` | query `unread_only=False`, `limit=50`(1-500) | list | 无 |
| GET | `/unread-count` | `26-30` | — | `{"count": int}` | 无 |
| PUT | `/{notification_id}/read` | `33-46` | path | `{"status":"ok"}` / 404 | emit `NotificationRead` |
| PUT | `/read-all` | `49-59` | — | `{"status":"ok"}` | emit `NotificationReadAll` |

## dashboard — `/api/dashboard`（[`api/dashboard.py`](../../backend/app/api/dashboard.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| GET | `` (即 `/api/dashboard`) | `15-25` | — | `{generated_at, data_sovereignty, active_goals, recent_events, recent_memories, timer_status, governance_status}` | 无（**只用 Kernel ABI**，一致性测试床） |

## system — `/api/system`（[`api/system.py`](../../backend/app/api/system.py)）

确认码常量（[`system.py`](../../backend/app/api/system.py)）：`EXPORT_CONFIRM="EXPORT_ALL_DATA"`、`DESTROY_CONFIRM="DESTROY_ALL_DATA"`、`IMPORT_CONFIRM="DESTROY_AND_IMPORT"`。

| 方法 | 路径 | 行 | 请求 | 响应 | Auth | 副作用 |
|---|---|---|---|---|---|---|
| GET | `/health` | `36-51` | — | `{status, service, version, auth_required, startup}`（未认证 startup 脱敏） | **public** | 无 |
| GET | `/live` | `54-60` | — | `{status:"ok", service}` | **public** | 无（Docker healthcheck） |
| GET | `/ready` | `63-74` | — | `{status:"ok",...}` / 503 | middleware | 探测 event_log 表 |
| GET | `/llm-providers` | `77-83` | — | `{providers, default}` | middleware | 无 |
| GET | `/info` | `86-106` | — | 表计数 + llm_providers 数 | middleware | 无 |
| GET | `/mcp-status` | `109-114` | — | MCP server 状态 | middleware | 无 |
| POST | `/export` | `117-126` | `ExportRequest{confirm=""}` | 完整快照（event_log + conversations + messages + counts） | middleware | DB 读 + activity_log 写 + `save_projection_snapshots()` |
| POST | `/import` | `129-138` | `ImportRequest{data, read_only=False, confirm=""}` | import 结果 | middleware | **destructive**：replay event_log + bootstrap chat |
| DELETE | `/data` | `141-151` | query `confirm` | `{status:"destroyed"}` | middleware | **不可逆**：删 SQLite + vectors + 重建空 DB |
| POST | `/export/encrypted` | `156-184` | `EncryptedExportRequest{password, confirm=""}` | `{format, data(base64), size_bytes}` | middleware | 线程池 PBKDF2(600k) + AES-GCM 加密 |
| POST | `/import/encrypted` | `187-209` | `EncryptedImportRequest{data, password, confirm=""}` | `{status, events_imported}` | middleware | 解密 + destructive import |
| GET | `/demo/model-continuity` | `214-225` | — | `{model, base_url, total_memories, total_events, message}` | middleware | 无 |

## settings — `/api/settings`（[`api/settings_api.py`](../../backend/app/api/settings_api.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| GET | `/llm` | `96-110` | — | LLM 配置（masked）+ presets | 无 |
| PUT | `/llm` | `113-144` | `UpdateLlmConfigRequest`（temperature 0-2, max_tokens>0） | 同上 | runtime_config 写 + `llm_router.reload()` |
| POST | `/llm/test` | `147-188` | `TestLlmRequest?` | `{ok, provider, model, latency_ms?, error?}` | **网络出口**：LLM ping |
| GET | `/email` | `191-199` | — | Gmail 配置（masked） | 无 |
| PUT | `/email` | `202-206` | `UpdateEmailConfigRequest` | `{config}` | runtime_config 写 |
| POST | `/email/test` | `209-259` | `TestEmailRequest?` | `{ok, imap_ok, smtp_ok, error?}` | **网络出口**：IMAP4_SSL + SMTP_SSL 登录 |
| GET | `/prompt` | `269-282` | — | `{identity, coding_rules, is_custom_*}` | 无 |
| PUT | `/prompt` | `285-314` | `PromptConfig{identity?, coding_rules?}` | `{ok: true}` | runtime_config 写 + **写文件** `backend/prompts/identity.md` & `coding_rules.md` |
| GET | `/notifications` | `325-337` | — | 通知渠道配置 | 无 |
| PUT | `/notifications` | `340-355` | `NotificationSettings{webhook_url, ntfy_topic, ntfy_server="https://ntfy.sh"}` | `{ok: true}` | runtime_config 写 + `notification_router.configure()` |

## telemetry — `/api/telemetry`（[`api/telemetry_api.py`](../../backend/app/api/telemetry_api.py)）

| 方法 | 路径 | 行 | 请求 | 响应 |
|---|---|---|---|---|
| GET | `/cost/summary` | `10-13` | query `days=7`(1-90) | LLM cost/token/latency 汇总 |
| GET | `/cost/by-model` | `16-19` | query `days=7` | 按 provider/model 分组 |
| GET | `/llm-calls` | `22-25` | query `limit=50`, `offset=0` | 最近 LLM 调用 |
| GET | `/tool-calls` | `28-31` | query `limit=50`, `tool_name?` | 工具调用列表 |
| GET | `/tool-summary` | `34-37` | query `days=7` | 工具成功率/延迟 |
| GET | `/memory/stats` | `40-43` | — | 记忆系统统计 |
| GET | `/health` | `46-49` | — | runtime 健康快照 |

## timeline — `/api/timeline`（[`api/timeline.py`](../../backend/app/api/timeline.py)）

| 方法 | 路径 | 行 | 请求 | 响应 |
|---|---|---|---|---|
| GET | `/events` | `113-167` | query `page=1`, `page_size=30`(1-100), `event_type?`, `date_from?`, `date_to?` | `{items, total, page, page_size, has_more, icons}`（每事件含中文 description + payload_snippet） |

`EVENT_LABELS`（[`timeline.py`](../../backend/app/api/timeline.py)）与 `EVENT_ICONS`（[`timeline.py`](../../backend/app/api/timeline.py)）把内部事件类型翻译为中文 + 图标。一次性拉最多 500 条 event_log 在 Python 中过滤/分页。

## knowledge — `/api/knowledge`（[`api/knowledge.py`](../../backend/app/api/knowledge.py)）

`MAX_FILE_SIZE=10MB`，`ALLOWED_EXTENSIONS={.pdf,.md,.txt,.markdown,.json,.csv}`（[`knowledge.py`](../../backend/app/api/knowledge.py)）。元数据存 `app_settings`（`category='knowledge_docs'`），向量化入 ChromaDB。

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| POST | `/upload` | `104-163` | multipart `file: UploadFile` | `{ok, document}` / 400 | 文件系统 + PyPDF2 提取 + 分块 + 向量化 + app_settings 写 |
| GET | `/documents` | `166-170` | — | `{documents, total}` | 无 |
| DELETE | `/documents/{document_id}` | `173-184` | path | `{ok: true}` / 404 | 删 ChromaDB chunks + app_settings |
| POST | `/search` | `187-193` | query `query`, `n_results=5`(1-20) | `{results, query, total}` | 读 ChromaDB |

## connectors — `/api/connectors`（[`api/connectors.py`](../../backend/app/api/connectors.py)）

| 方法 | 路径 | 行 | 请求 | 响应 | 副作用 |
|---|---|---|---|---|---|
| GET | `/` | `55-95` | — | `{connectors: builtin[] + external[]}` | 无 |
| GET | `/{connector_name}` | `98-127` | path | connector 详情（含 tools） / 404 | 无 |
| POST | `/{connector_name}/test` | `147-168` | path | `{status, message}` / test result / 404 | 可能 MCP 连接测试（进程间/网络） |
| GET | `/registry` | `187-190` | — | `{servers, total}`（读 `mcp_registry.json`） | 无 |
| POST | `/install` | `193-219` | `InstallConnectorRequest{name, config={}}` | `{ok, message, server}` | **写文件** `mcp_config.json` |
| POST | `/uninstall` | `222-236` | body `{name: str}` | `{ok, message}` | **写文件** `mcp_config.json` |

## WebSocket

| 路径 | 行 | 用途 |
|---|---|---|
| `WS /ws` | [`main.py`](../../backend/app/main.py) | 实时通知推送。客户端发 `ping` 得 `pong`；`broadcast_notification` 向所有连接广播 JSON。鉴权 `Sec-WebSocket-Protocol: auth.<token>` |

## 未挂载的 workflows router

> `backend/app/api/workflows.py` 定义了 `GET/POST/PUT/DELETE /api/workflows[/{id}]`、`/export`、`/_palette`、`/templates`、`/from-template/{id}`，但 `main.py` **未 include_router**。当前运行实例不可达。
