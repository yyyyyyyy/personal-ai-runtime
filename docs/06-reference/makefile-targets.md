# Makefile 目标参考

全 [`Makefile`](../../Makefile) 目标清单。Windows 等价见 [`Makefile.ps1`](../../Makefile.ps1)（子集，见末尾）。

## 安装与初始化

| 目标 | 命令 | 说明 |
|---|---|---|
| `install` | `Makefile:8-13` | `pip install -r backend/requirements.txt` + `npm ci`（frontend+desktop）+ `python3 generate_icon.py`（desktop）+ `alembic upgrade head`（失败容错） |
| `setup` | `Makefile:16-17` | `bash install.sh`（交互式完整安装） |
| `init-db` | `Makefile:19-20` | `alembic upgrade head`（失败容错，提示首次运行 auto-init） |
| `install-hooks` | `Makefile:22-23` | `bash scripts/install_hooks.sh`（设 `core.hooksPath=.githooks`） |

## 开发

| 目标 | 命令 | 说明 |
|---|---|---|
| `dev` | `Makefile:25-30` | 后台启 uvicorn（8000）+ `wait_for_health.sh` 门控 + vite（5173），`wait` 阻塞 |
| `demo` | `Makefile:32-33` | `LLM_API_KEY=${LLM_API_KEY:-demo-seed} python3 scripts/seed_demo.py` |
| `screenshots` | `Makefile:35-36` | `cd docs/assets && npm install && npx playwright install chromium && npm run screenshots` |
| `desktop` | `Makefile:60-61` | `cd desktop && npm start` |
| `desktop-build` | `Makefile:63-64` | `cd desktop && npm run build`（electron-builder） |

## 测试

| 目标 | 命令 | 说明 |
|---|---|---|
| `test` | `Makefile:38` | = `test-backend test-frontend` |
| `test-backend` | `Makefile:40-41` | `pytest tests/ -q -m "not live_llm"` |
| `test-frontend` | `Makefile:43-44` | `tsc --noEmit && npm test` |
| `test-e2e` | `Makefile:46-47` | `npx playwright install chromium && npm run test:e2e` |

## 质量门

| 目标 | 命令 | 说明 |
|---|---|---|
| `lint` | `Makefile:49-50` | `ruff check app/` |
| `typecheck` | `Makefile:54-55` | `mypy app/ scripts/ --ignore-missing-imports` |
| `ci-local` | `Makefile:57-58` | 聚合：`lint typecheck test-backend test-frontend test-e2e boundary execution-ownership projection-provenance conversation-rebuild export-roundtrip-verify` |

## 架构不变量验证

| 目标 | 脚本 | 说明 |
|---|---|---|
| `boundary` | [`check_boundary.py`](../../backend/scripts/check_boundary.py) | Kernel 边界静态扫描（新违规失败） |
| `boundary-inventory` | 同上 `--inventory` | 列全部匹配，退出 0 |
| `boundary-strict` | 同上 `--strict` | 连 allowlist 债也失败 |
| `execution-ownership` | [`check_execution_ownership.py`](../../backend/scripts/check_execution_ownership.py) | `invoke_capability` 必带 `execution_id` |
| `execution-ownership-inventory` | 同上 `--inventory` | 列全部 |
| `execution-ownership-strict` | 同上 `--strict` | 连 bypass 债也失败 |
| `projection-provenance` | [`check_projection_provenance.py`](../../backend/scripts/check_projection_provenance.py) | 投影行有对应 event_log 事件 |
| `conversation-rebuild` | [`verify_conversation_rebuild.py`](../../backend/scripts/verify_conversation_rebuild.py) | 对话消息可重建且可溯源 |
| `goal-rebuild` | [`verify_goal_rebuild.py`](../../backend/scripts/verify_goal_rebuild.py) | 目标 parent_id/progress 重建后保留 |
| `rebuild-verify` | [`verify_rebuild.py`](../../backend/scripts/verify_rebuild.py) | 旗舰：全量重建字节一致 |
| `export-roundtrip-verify` | [`verify_export_roundtrip.py`](../../backend/scripts/verify_export_roundtrip.py) | export → import 无损 |
| `snapshot-verify` | [`verify_snapshot_rebuild.py`](../../backend/scripts/verify_snapshot_rebuild.py) | 增量重建 + checkpoint 不回退 |
| `egress-verify` | [`verify_egress.py`](../../backend/scripts/verify_egress.py) | LLM 出口审计 |
| `vector-consistency-verify` | [`verify_vector_consistency.py`](../../backend/scripts/verify_vector_consistency.py) | SQLite memories vs Chroma 对账 |
| `connector-verify` | [`verify_connector.py`](../../backend/scripts/verify_connector.py) | 日历连接器审计 |
| `alembic-verify` | [`verify_alembic.py`](../../backend/scripts/verify_alembic.py) | 19 张必需表存在 + PRAGMA foreign_keys |

## 容器

| 目标 | 命令 | 说明 |
|---|---|---|
| `docker-up` | `Makefile:115-116` | `docker compose up --build` |
| `docker-down` | `Makefile:118-119` | `docker compose down` |

## 锁文件与密钥扫描

| 目标 | 命令 | 说明 |
|---|---|---|
| `lockfile` | `Makefile:123-126` | `pip-compile --generate-hashes --output-file requirements.lock requirements.txt`（生成带哈希锁文件，提交后 CI 安装相同版本） |
| `secrets-scan` | `Makefile:130-132` | `gitleaks detect --config .gitleaks.toml --source . --no-banner --redact`（未装则提示安装链接） |

## Makefile.ps1（Windows 子集）

[`Makefile.ps1`](../../Makefile.ps1) 用 `switch` on `$Task`，提供：`help`、`install`、`install-hooks`、`dev`（手动两终端）、`test-backend`、`test-frontend`、`lint`、`typecheck`、`boundary`、`docker-up`、`docker-down`。未知任务报错。

注意差异：

- `typecheck` 的 agents 文件列表不同（`planner.py`/`critic.py`/`llm_router.py` vs Unix 的 `llm_failover.py`/`conversation.py`/`memory_engine.py`/`memory_extractor.py`），且包含 `app/product/`、`app/api/`、`app/main.py`。
- Windows 不提供 verify 脚本目标（仅 `boundary`）与 ci-local 聚合。

## 根级脚本（非 Make 目标）

| 脚本 | 用途 |
|---|---|
| [`install.sh`](../../install.sh) | 交互式安装向导（`make setup` 调用） |
| [`scripts/install_hooks.sh`](../../scripts/install_hooks.sh) / [`.ps1`](../../scripts/install_hooks.ps1) / [`install-hooks.cmd`](../../install-hooks.cmd) | git hook 安装 |
| [`scripts/wait_for_health.sh`](../../scripts/wait_for_health.sh) | 轮询健康端点（`make dev` 用） |
| [`scripts/soak_recovery.py`](../../scripts/soak_recovery.py) | ADR-0007 Step 3 崩溃恢复 soak 测试 |
| [`scripts/soak_trigger.py`](../../scripts/soak_trigger.py) | 累积执行 soak 测试 |
| [`scripts/soak_stats.py`](../../scripts/soak_stats.py) | soak 只读报告 |
