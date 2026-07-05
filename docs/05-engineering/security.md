# 安全

本文档描述 Personal AI Runtime 的安全机制。所有机制均依据源码事实。

## 认证

### HTTP Bearer Token

[`backend/app/main.py`](../../backend/app/main.py) 的 `AuthMiddleware`（[`main.py`](../../backend/app/main.py)）是纯 ASGI 中间件（刻意避开 `BaseHTTPMiddleware` 以免缓冲 SSE 流）。

- `settings.auth_token` 为空时直接放行（认证关闭）。
- 启用时，从 `Authorization: Bearer <token>` 提取，`secrets.compare_digest` 比对；失败返回 401 JSON。
- 跳过路径 `SKIP_AUTH_PATHS`（[`main.py`](../../backend/app/main.py)）：`/`、`/api/system/health`、`/api/system/live`、`/docs`、`/redoc`、`/openapi.json`（前缀匹配，`/` 精确匹配）。
- 启用时同时触发限流。

### 启动安全策略

`lifespan`（[`main.py`](../../backend/app/main.py)）：未设 `AUTH_TOKEN` 且非 localhost bind（`_is_localhost_bind` 判定 `127.0.0.1`/`::1`/`localhost`/`127.*`）且未开 `ALLOW_NO_AUTH_ON_EXPOSED` → `sys.exit(1)` 拒绝启动。裸奔运行时启动周期性 600s 安全告警协程。

### WebSocket 认证

`WS /ws`（[`main.py`](../../backend/app/main.py)）经 `Sec-WebSocket-Protocol: auth.<token>` 子协议携带 token（[`main.py`](../../backend/app/main.py)），失败关闭码 4401，成功回 `auth.ok` 子协议。

## 限流

[`backend/app/core/rate_limit.py`](../../backend/app/core/rate_limit.py) 内存令牌桶（按端点前缀），仅在 `AuthMiddleware` 启用认证时检查（[`main.py`](../../backend/app/main.py)）：

| 端点前缀 | 限额 |
|---|---|
| `/api/chat` | 30 req / 60s |
| `/api/settings/llm/test` | 5 / 60s |
| `/api/settings/email/test` | 5 / 60s |
| `/api/inbox/poll` | 10 / 60s |
| `/api/system/export` | 3 / 60s |

超限返回 429。

## 能力治理

所有工具调用经 `Kernel.invoke_capability` 走 4-gate 授权。写类工具需用户审批；外部内容（邮件、网页）触发 taint 标记。详见 [02-concepts/capability-governance.md](../02-concepts/capability-governance.md)。

策略种子 [`backend/capability_policy.json`](../../backend/capability_policy.json)：

- **needs_user**（9 个写工具）：`apply_patch`、`write_file`、`add_calendar_event`、`send_email`、`shell_exec`、`telegram_send`、`computer_click`/`type`/`key`。
- 审批 24h TTL，RuntimeLoop 每 ~10s 过期。
- `correlation_id` 被 taint 时，写类工具强制 high 风险（防提示注入）。

## 执行归属

每次 `invoke_capability` 必须带 `execution_id`（[`backend/scripts/check_execution_ownership.py`](../../backend/scripts/check_execution_ownership.py) CI 强制）。`agent:*`/`scheduler`/`executor`/`background` 类 actor 在 `execution_scope` 未绑定时被拒。保证所有工具调用可归属到 `handler_executions` 记录，用于崩溃恢复与审计。

## 出口审计

[`backend/app/core/runtime/egress/egress_gate.py`](../../backend/app/core/runtime/egress/egress_gate.py) 的 `prepare_llm_egress(messages, purpose, actor)` 在每次 LLM 调用前审计——**messages 原样通过，不做脱敏**——发出 `EgressApproved` 事件，分类为 `identity_surface`/`memory_context`/`trajectory_context`/`general`。

Brain 与 BrainCompletionMixin 在每次 LLM 调用前调用。MemoryExtractor 云路径用 `purpose="memory_extract"`。验证：[`scripts/verify_egress.py`](../../backend/scripts/verify_egress.py)。

## SSRF 防护

URL 抓取类工具经 `url_safety.validate_http_url` 校验。相关测试：`test_browser_ssrf.py`、`test_fetch_ssrf.py`、`test_url_safety.py`。MCPMesh 的 `call_tool` 对 Playwright URL 工具同样校验。

## 文件系统隔离

`filesystem` 内建工具受 `settings.filesystem_allowed_dirs`/`filesystem_protected_paths` 限制。默认保护路径含 `kernel/`、`policy`、`taint.py`、`.env*`、`.git/`（见 [`backend/prompts/coding_rules.md`](../../backend/prompts/coding_rules.md)）。`shell_exec` 工具受同一治理（needs_user）。

## 加密导出

[`backend/app/product/encrypted_sync.py`](../../backend/app/product/encrypted_sync.py)：

- 算法：AES-GCM + PBKDF2-HMAC-SHA256（600k 迭代）。
- blob 布局：`[16B salt][12B nonce][ciphertext + 16B tag]`，base64 编码。
- `BLOB_FORMAT = "encrypted_snapshot_v1"`。
- 最小密码 8 字符。
- 异步执行（线程池），避免阻塞事件循环。

经 `POST /api/system/export/encrypted` 与 `/api/system/import/encrypted` 暴露。确认码 `EXPORT_CONFIRM="EXPORT_ALL_DATA"` / `IMPORT_CONFIRM="DESTROY_AND_IMPORT"`。

## 数据主权操作

| 端点 | 操作 | 风险 |
|---|---|---|
| `POST /api/system/export` | 明文 JSON 导出（event_log + conversations + messages + counts） | 只读 + activity_log 写 |
| `POST /api/system/export/encrypted` | 加密导出 | 只读 |
| `POST /api/system/import` | replay event_log + bootstrap chat | **destructive**（`read_only=false` 时） |
| `POST /api/system/import/encrypted` | 解密 + destructive import | **destructive** |
| `DELETE /api/system/data?confirm=DESTROY_ALL_DATA` | 删 SQLite 文件 + vectors 目录 + 重建空 DB | **不可逆** |

## 密钥扫描

[`.gitleaks.toml`](../../.gitleaks.toml) 在 CI（`secrets-scan` job）与本地（`make secrets-scan`）扫描工作树。allowlist 覆盖 `.env.example`、`docs/*.md`、`README*.md`、`CONTRIBUTING.md` 与已知占位符（`your-deepseek-api-key`、`sk-test-key`、`demo-seed` 等）。

## CORS

`CORSMiddleware`（[`main.py`](../../backend/app/main.py)）：`allow_origins=settings.cors_origins.split(",")`（默认 `http://localhost:5173,http://localhost:5174`）、`allow_credentials=True`、方法 `GET/POST/PUT/PATCH/DELETE/OPTIONS`、头 `Authorization/Content-Type/X-Request-ID`、暴露 `X-Request-ID`。

## 不在本仓库实现的安全特性

代码库中证据不足：以下常见安全特性未观察到实现，文档不做推测——

- HTTPS/TLS 终止（依赖外部反向代理）。
- 用户账号体系（单用户设计，仅单一 `AUTH_TOKEN`）。
- 审计日志的不可篡改存储（`activity_log` 是 APP_STORAGE，可直访；`event_log` 才是 append-only）。
- 速率限制的持久化（内存令牌桶，重启重置）。
