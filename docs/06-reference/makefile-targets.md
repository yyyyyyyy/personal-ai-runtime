# Makefile 目标参考

全 [`Makefile`](../../Makefile) 目标清单。Windows 等价见 [`Makefile.ps1`](../../Makefile.ps1)（子集，见末尾）。

## 安装与初始化

| 目标 | 命令 | 说明 |
|---|---|---|
| `install` | `Makefile` | 先运行 `dependency-sync`，再以 `--require-hashes` 安装 backend lock，执行 frontend/desktop `npm ci` 与数据库迁移 |
| `setup` | `Makefile:16-17` | `bash install.sh`（交互式完整安装） |
| `init-db` | `Makefile:19-20` | `alembic upgrade head`（失败容错，提示首次运行 auto-init） |
| `install-hooks` | `Makefile:22-23` | `bash scripts/install_hooks.sh`（设 `core.hooksPath=.githooks`） |

## 开发

| 目标 | 命令 | 说明 |
|---|---|---|
| `dev` | `Makefile:25-30` | 后台启 uvicorn（8000）+ `wait_for_health.sh` 门控 + vite（5173），`wait` 阻塞 |
| `demo` | `Makefile` | `LLM_API_KEY=${LLM_API_KEY:-demo-seed} python3 -m scripts.seed_demo` |
| `screenshots` | `Makefile:35-36` | `cd docs/assets && npm install && npx playwright install chromium && npm run screenshots` |
| `desktop` | `Makefile:60-61` | `cd desktop && npm start` |
| `desktop-build` | `Makefile:63-64` | `cd desktop && npm run build`（electron-builder） |

## 测试

| 目标 | 命令 | 说明 |
|---|---|---|
| `test` | `Makefile:38` | = `test-backend test-frontend` |
| `test-backend` | `Makefile:40-41` | `pytest tests/ -q -m "not live_llm"` |
| `test-backend-coverage` | `Makefile` | CI coverage 测试，并执行 runtime ≥75%、API ≥50% 门限 |
| `test-frontend` | `Makefile:43-44` | `tsc --noEmit && npm test` |
| `test-e2e` | `Makefile:46-47` | `npx playwright install chromium && npm run test:e2e` |
| `test-e2e-real` | `Makefile` | 真实 backend + fake LLM 的 SSE/审批 Playwright |
| `desktop-test` | `Makefile` | 运行 desktop vitest smoke，不构建安装包 |

## 质量门

| 目标 | 命令 | 说明 |
|---|---|---|
| `lint` | `Makefile:49-50` | `ruff check app/` |
| `typecheck` | `Makefile:54-55` | `mypy app/ scripts/ --ignore-missing-imports` |
| `dependency-sync` | `Makefile` | 检查 `pyproject.toml` dependencies 与权威 `requirements.txt` 完全一致 |
| `backend-compileall` | `Makefile` | `python3 -m compileall app/ -q` |
| `backend-smoke` | [`verify_api_mcp_smoke.py`](../../backend/scripts/verify_api_mcp_smoke.py) | 验证核心 API 路由与 MCP 工具/安全标志（CORE 注册表派生 + CRITICAL 钉选） |
| `backend-ci-static` | `Makefile` | 静态门禁并行波次（`make -j$(JOBS)`） |
| `backend-ci-runtime` | `Makefile` | 运行时 verify / coverage 并行波次 |
| `backend-ci-core` | `Makefile` | 先 static 再 runtime；GitHub Actions 与本地共用入口 |
| `ci-local` | `Makefile` | `backend-ci-core` + frontend 单测/E2E/real-E2E + desktop smoke |

## 架构不变量验证

| 目标 | 脚本 | 说明 |
|---|---|---|
| `boundary` | [`check_boundary.py`](../../backend/scripts/check_boundary.py) | Kernel 边界静态扫描（新违规失败） |
| `boundary-inventory` | 同上 `--inventory` | 列全部匹配，退出 0 |
| `boundary-strict` | 同上 `--strict` | 连 allowlist 债也失败 |
| `layer-deps` | [`check_layer_deps.py`](../../backend/scripts/check_layer_deps.py) | Runtime/Product/Store/API 职责边（新违规失败） |
| `layer-deps-inventory` | 同上 `--inventory` | 列全部跨层 import，退出 0 |
| `layer-deps-strict` | 同上 `--strict` | 连 DEBT_ALLOWLIST 债也失败 |
| `execution-ownership` | [`check_execution_ownership.py`](../../backend/scripts/check_execution_ownership.py) | `invoke_capability` 必带 `execution_id` |
| `execution-ownership-inventory` | 同上 `--inventory` | 列全部 |
| `execution-ownership-strict` | 同上 `--strict` | 连 bypass 债也失败 |
| `projection-provenance` | [`check_projection_provenance.py`](../../backend/scripts/check_projection_provenance.py) | 投影行有对应 event_log 事件 |
| `docs-links` | [`check_doc_links.py`](../../backend/scripts/check_doc_links.py) | 文档相对链接与路径存在 |
| `docs-table-sync` | [`check_doc_table_sync.py`](../../backend/scripts/check_doc_table_sync.py) | 文档表清单与 registry 同步 |
| `docs-line-refs` | [`check_doc_line_refs.py`](../../backend/scripts/check_doc_line_refs.py) | 禁止易漂移的 Python 行号引用 |
| `policy-consistency` | [`check_capability_policy_consistency.py`](../../backend/scripts/check_capability_policy_consistency.py) | capability policy 与运行时声明一致 |
| `conversation-rebuild` | [`verify_conversation_rebuild.py`](../../backend/scripts/verify_conversation_rebuild.py) | 对话消息可重建且可溯源 |
| `goal-rebuild` | [`verify_goal_rebuild.py`](../../backend/scripts/verify_goal_rebuild.py) | 目标 parent_goal_id/progress 重建后保留 |
| `work-items-goal-rebuild` | [`verify_work_items_goal_rebuild.py`](../../backend/scripts/verify_work_items_goal_rebuild.py) | work_items 目标字段与进度可重建 |
| `rebuild-verify` | [`verify_rebuild.py`](../../backend/scripts/verify_rebuild.py) | 旗舰：全量重建字节一致 |
| `export-roundtrip-verify` | [`verify_export_roundtrip.py`](../../backend/scripts/verify_export_roundtrip.py) | export → import 无损 |
| `snapshot-verify` | [`verify_snapshot_rebuild.py`](../../backend/scripts/verify_snapshot_rebuild.py) | 增量重建 + checkpoint 不回退 |
| `memory-lifecycle-verify` | [`verify_memory_lifecycle.py`](../../backend/scripts/verify_memory_lifecycle.py) | memory 更新、删除与重建生命周期 |
| `inbox-audit-verify` | [`verify_inbox_audit.py`](../../backend/scripts/verify_inbox_audit.py) | inbox caused_by 审计链 |
| `egress-verify` | [`verify_egress.py`](../../backend/scripts/verify_egress.py) | LLM 出口审计 |
| `vector-consistency-verify` | [`verify_vector_consistency.py`](../../backend/scripts/verify_vector_consistency.py) | SQLite memories vs Chroma 对账 |
| `connector-verify` | [`verify_connector.py`](../../backend/scripts/verify_connector.py) | 日历连接器审计 |
| `memory-repair-verify` | [`verify_memory_index_repairs.py`](../../backend/scripts/verify_memory_index_repairs.py) | durable repair queue 自测 |
| `tool-calls-audit-verify` | [`verify_tool_calls_audit.py`](../../backend/scripts/verify_tool_calls_audit.py) | tool_calls ↔ Capability* 事件 1:1 |
| `alembic-verify` | [`verify_alembic.py`](../../backend/scripts/verify_alembic.py) | ephemeral DB 上校验 `ALL_CLASSIFIED_TABLES` + PRAGMA foreign_keys |

## 容器

| 目标 | 命令 | 说明 |
|---|---|---|
| `docker-up` | `Makefile:115-116` | `docker compose up --build` |
| `docker-down` | `Makefile:118-119` | `docker compose down` |

## 锁文件与密钥扫描

| 目标 | 命令 | 说明 |
|---|---|---|
| `lockfile` | `Makefile` | 固定 `pip-tools==7.5.3`，生成带包哈希和输入文件 SHA-256 的 `requirements.lock` |
| `secrets-scan` | `Makefile:130-132` | `gitleaks detect --config .gitleaks.toml --source . --no-banner --redact`（未装则提示安装链接） |

## Makefile.ps1（Windows）

[`Makefile.ps1`](../../Makefile.ps1) 用 `switch` on `$Task`，提供：`help`、`install`、`install-hooks`、`test-backend`、`test-frontend`、`lint`、`typecheck`、`boundary`、`layer-deps`、`backend-ci-static`、`backend-ci-runtime`、`backend-ci-core`、`docker-up`、`docker-down`。

注意差异：

- 脚本统一通过 `python -m scripts.<name>` 调用（与 Makefile 一致）。
- Unix `make backend-ci-core` 两波 `-j` 并行；PowerShell 为可靠退出码改为顺序执行。需要并行时用 make/WSL。
- Windows `backend-ci-runtime` 跑 pytest 全量（非 coverage 门限），verify 清单与 Makefile 对齐。

## 根级脚本（非 Make 目标）

| 脚本 | 用途 |
|---|---|
| [`install.sh`](../../install.sh) | 交互式安装向导（`make setup` 调用） |
| [`scripts/install_hooks.sh`](../../scripts/install_hooks.sh) / [`.ps1`](../../scripts/install_hooks.ps1) / [`install-hooks.cmd`](../../install-hooks.cmd) | git hook 安装 |
| [`scripts/wait_for_health.sh`](../../scripts/wait_for_health.sh) | 轮询健康端点（`make dev` 用） |
| [`scripts/soak_recovery.py`](../../scripts/soak_recovery.py) | Execution 契约 §3 崩溃恢复 soak 测试 |
| [`scripts/soak_trigger.py`](../../scripts/soak_trigger.py) | 累积执行 soak 测试 |
| [`scripts/soak_stats.py`](../../scripts/soak_stats.py) | soak 只读报告 |
