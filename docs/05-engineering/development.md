# 开发指南

本文档描述如何搭建本地开发环境与日常开发循环。

## 前置依赖

[`install.sh`](../../install.sh) 检查并要求：

- **Python ≥ 3.12**（[`backend/pyproject.toml`](../../backend/pyproject.toml) 的 `requires-python = ">=3.12"`）
- **Node ≥ 20**（CI 用 Node 20，见 [ci-cd.md](ci-cd.md)）
- **npm**

可选：

- **Ollama**（本地记忆抽取，`MEMORY_EXTRACTOR=ollama`）
- **Docker**（容器化部署，见 [deployment.md](deployment.md)）
- **gitleaks**（密钥扫描，`make secrets-scan`）

## 首次安装

### 交互式（推荐）

```bash
bash install.sh
```

[`install.sh`](../../install.sh) 五段式：

1. 检查 python3/node/npm 版本。
2. 若 `.env` 不存在，复制 `.env.example`，交互式提示选 LLM provider（DeepSeek 默认 / OpenAI / 自定义 OpenAI 兼容）+ API key + base URL + model，可选 Gmail 凭据。若 `.env` 存在但 `LLM_API_KEY` 不以 `sk-` 开头则警告。
3. 安装后端 pip、前端 npm（`npm ci` → 失败回退 `npm install`）、desktop npm（若存在）。
4. 跑 `alembic upgrade head`（首次运行可能由应用 auto-init）。
5. 验证 `from app.main import app` 可导入，打印启动说明。

### 手动

```bash
make install
```

等价于：先检查后端依赖元数据同步，再执行 `pip install --require-hashes -r backend/requirements.lock` + `npm ci`（frontend + desktop）+ `python3 generate_icon.py`（desktop）+ `alembic upgrade head`（失败容错）。锁文件同时包含运行时依赖和 pytest/ruff/mypy 等开发工具。

## 环境配置

复制 `.env.example` 到 `.env` 并填值。最小必需：`LLM_API_KEY`。详见 [04-data/configuration.md](../04-data/configuration.md)。

## 日常开发循环

### 启动开发服务器

```bash
make dev
```

[`Makefile:25-30`](../../Makefile) 行为：

1. 后台启 `cd backend && python3 -m uvicorn app.main:app --reload --port 8000`。
2. 跑 [`scripts/wait_for_health.sh`](../../scripts/wait_for_health.sh) 轮询 `http://localhost:8000/api/system/health`（每秒一次，最多 60s）。
3. 健康后启 `cd frontend && npm run dev`（Vite 5173）。
4. `wait` 阻塞，Ctrl+C 同时停两者。

前端经 Vite proxy 把 `/api` 与 `/ws` 转发到后端（[`frontend/vite.config.ts:11-28`](../../frontend/vite.config.ts)）。

### 桌面端

另开终端：

```bash
make desktop      # cd desktop && npm start  (electron .)
```

Electron 默认加载 `http://localhost:5173`，探测 8000 端口已有后端则复用。详见 [03-subsystems/desktop.md](../03-subsystems/desktop.md)。

### 数据库迁移

```bash
make init-db      # alembic upgrade head（失败容错）
```

迁移文件见 [04-data/data-model.md](../04-data/data-model.md) 的 Alembic 段。

### 演示数据

```bash
make demo         # LLM_API_KEY=${LLM_API_KEY:-demo-seed} python3 scripts/seed_demo.py
```

[`scripts/seed_demo.py`](../../backend/scripts/seed_demo.py) 幂等：检查目标 `【Demo】完成用户验证访谈` 是否已存在，不存在则播种 2 个目标 + 2 条记忆 + 1 个对话 + 1 条消息。

## 质量门

### Lint

```bash
make lint         # cd backend && ruff check app/
```

ruff 配置（[`backend/pyproject.toml`](../../backend/pyproject.toml)）：`line-length = 100`、`target-version = "py312"`、select `["E","F","W","I"]`、ignore `["E501"]`。

### Typecheck

```bash
make typecheck    # cd backend && mypy app/ scripts/ --ignore-missing-imports
```

mypy 配置：`python_version = "3.12"`、`ignore_missing_imports = true`、`check_untyped_defs = true`、`follow_imports = "normal"`。

前端类型检查：`cd frontend && npx tsc --noEmit`（`make test-frontend` 包含）。

### 本地完整 CI 等价

```bash
make ci-local
```

聚合任务复用 GitHub Actions 调用的 `make backend-ci-core`，再执行 frontend 单测/E2E 与 desktop smoke。后端清单只在 Makefile 的 `BACKEND_CI_TARGETS` 维护，包含 dependency sync、compileall、lint、typecheck、coverage 测试和全部架构不变量。`dependency-sync` 强制 [`backend/pyproject.toml`](../../backend/pyproject.toml) 的 `[project].dependencies` 与权威文件 [`backend/requirements.txt`](../../backend/requirements.txt) 完全一致（包括顺序和 exact pins）。

## 测试矩阵

详见 [testing.md](testing.md)。速查：

| 命令 | 内容 |
|---|---|
| `make test` | backend + frontend 单测 |
| `make test-backend` | `pytest tests/ -q -m "not live_llm"` |
| `make test-frontend` | `tsc --noEmit && npm test` |
| `make test-e2e` | Playwright（先 `npx playwright install chromium`） |
| `make test-e2e-real` | 真实 backend + fake LLM 的 SSE/审批 Playwright |

## 不变量验证

架构不变量由独立脚本强制，详见 [testing.md](testing.md) 与 [06-reference/makefile-targets.md](../06-reference/makefile-targets.md)。常用：

```bash
make boundary                  # Kernel 边界静态扫描
make execution-ownership       # invoke_capability 必带 execution_id
make projection-provenance     # 投影行有对应 event_log 事件
make rebuild-verify            # 全量重建字节一致
make vector-consistency-verify # SQLite memories vs Chroma 对账
```

## Git 钩子

```bash
make install-hooks     # bash scripts/install_hooks.sh
```

设置 `core.hooksPath=.githooks`。两个钩子：

- **pre-commit**：收集暂存的 backend `.py`，跑 `ruff check` + `mypy app/ scripts/`。
- **commit-msg**：强制 Conventional Commits（`^(feat|fix|docs|style|refactor|perf|test|chore|revert)(\(...\))?: .{2,100}$`），拒绝以句号结尾的 subject。

详见 [ci-cd.md](ci-cd.md)。

## 调试

### 后端日志

structlog + stdlib（[`backend/app/core/logging_config.py`](../../backend/app/core/logging_config.py)）。`_request_id_processor` 把 `request_id_var` 附到每行日志，由 `RequestIDMiddleware X-Request-ID` 头驱动。

### 启动健康检查

`GET /api/system/health` 返回 `{status, service, version, auth_required, startup}`。未通过认证时 startup 经 `sanitize_startup_for_public` 脱敏。`GET /api/system/live` 是 Docker healthcheck 端点（公开）。

### MCP 状态

`GET /api/system/mcp-status` 返回每服务器 connected/lazy/disconnected/unavailable。

### 仪表盘

`GET /api/dashboard` 是一致性测试床，每个 widget 只用 Kernel ABI。前端 `/dashboard` 页可视化。

### 数据主权检查

`/trust` 页或 `scripts/demo_data_sovereignty.py`（需后端运行）展示存储位置、API、export/rebuild 命令。

## 锁文件

运行时直接依赖以 [`backend/requirements.txt`](../../backend/requirements.txt) 为权威；[`backend/requirements-dev.txt`](../../backend/requirements-dev.txt) 在其上追加最小 CI/开发工具集。两者都使用 exact pins。

```bash
make lockfile
```

该目标固定使用 `pip-tools==7.5.3`，从 `requirements-dev.txt` 生成 [`backend/requirements.lock`](../../backend/requirements.lock)，并在 lock 头部写入两个依赖输入文件的 SHA-256。安装前同步检查会验证这些摘要，因此新增、修改或删除依赖后未重新生成 lock 都会失败。CI、本地 `make install` 和 `install.sh` 均使用 `python3 -m pip install --require-hashes -r requirements.lock`，因此运行时、测试、覆盖率、lint 和类型检查工具共享同一套可校验安装结果。

Chroma 使用 `chromadb==1.5.9`（自带 Windows/macOS/Linux 二进制包，不再依赖 `chroma-hnswlib` 编译），并在 [`vector.py`](../../backend/app/store/vector.py) 显式钉死 `DefaultEmbeddingFunction`（ONNX MiniLM L6 v2，384 维），避免升级时静默换模型。若从 `0.5.x` 升级后出现维度/打开失败：备份 `VECTOR_DIR`，删除向量目录后重启以重建索引，或执行一次完整 restore/`rebuild_all` 触发全量 reconcile。Windows 专用条件依赖（如 `colorama`、`pyreadline3`、`pywin32`、跳过 `uvloop`）由权威输入 + stamp 合并进同一份 lock；CI 的 `dependency-platforms` job 会在 ubuntu/macOS/Windows 上安装并做 import 冒烟。

修改运行时依赖时应同步更新 `requirements.txt` 与 `pyproject.toml`，然后运行：

```bash
make dependency-sync
make lockfile
```

## 密钥扫描

```bash
make secrets-scan
```

[`Makefile:130-132`](../../Makefile)：`gitleaks detect --config .gitleaks.toml --source . --no-banner --redact`。规则见 [`.gitleaks.toml`](../../.gitleaks.toml)，允许 `.env.example`/`docs/*.md` 中的占位符。
