# CI / CD

本文档描述持续集成与发布的全部配置。

## GitHub Actions 工作流

### `workflows/ci.yml`

push/PR 到 `main` 时触发，三个 job：

**`secrets-scan` job**：`gitleaks/gitleaks-action@v3`，配置 [`.gitleaks.toml`](../../.gitleaks.toml)，`fetch-depth: 0`。

**`backend` job**（Python 3.12）：

1. `pip install -r requirements.txt` + pytest/ruff/mypy/coverage 工具。
2. `compileall app/`（字节编译检查）。
3. `ruff check app/`。
4. `mypy app/ scripts/`。
5. `pytest tests/ -v --cov=app/core/runtime --cov=app/core/harness --cov=app/api -m "not live_llm"`，两个 `--fail-under` 门：`app/core/runtime/*` ≥75%、`app/api/*` ≥50%。
6. 顺序跑：`verify_alembic.py` → 内联 MCP 工具存在性检查（26 个命名内建工具 + confirmation/async 标志）→ 内联 API 路由加载检查（14 个端点前缀）→ `verify_rebuild.py`、`verify_export_roundtrip.py`、`verify_snapshot_rebuild.py`、`check_boundary.py`、`check_execution_ownership.py`、`check_projection_provenance.py`、`verify_conversation_rebuild.py`、`verify_goal_rebuild.py`、`verify_memory_lifecycle.py`、`verify_inbox_audit.py`、`verify_egress.py`、`verify_connector.py`、`verify_vector_consistency.py`。

**`frontend` job**（Node 20）：

1. `npm install`。
2. `tsc --noEmit`。
3. `npm run lint`（`eslint src/ && prettier --check src/`）。
4. `npm test`（vitest）。
5. `npm run build`（`tsc -b && vite build`）。
6. `npx playwright install chromium`。
7. `npm run test:e2e`。

### `workflows/release.yml`

tag `v*.*.*` 触发：

1. 提取版本号。
2. 内联 Python 脚本从 `CHANGELOG.md` 切出对应版本段落。
3. `softprops/action-gh-release@v3` 创建 GitHub Release。
4. tag 含 `-` 标记为 prerelease。

> 代码库中证据不足：`CHANGELOG.md` 在当前仓库未观察到。release 工作流依赖该文件，若缺失切版本段落会失败。

## Dependabot

[`.github/dependabot.yml`](../../.github/dependabot.yml)：

- **每周一**：`pip`（backend，label `deps(backend)`）、`npm`（frontend，label `deps(frontend)`）、`npm`（desktop，label `deps(desktop)`）。
- **每月**：`github-actions`（label `deps(ci)`）。

## Git Hooks

[`.githooks/`](../../.githooks/) + 安装脚本 [`scripts/install_hooks.sh`](../../scripts/install_hooks.sh) / [`scripts/install_hooks.ps1`](../../scripts/install_hooks.ps1) / [`install-hooks.cmd`](../../install-hooks.cmd)（Windows shim，绕过执行策略调 PowerShell 安装器）。

安装：`make install-hooks`（设 `core.hooksPath=.githooks` 并 chmod）。

### `pre-commit`

收集暂存的 backend `.py`（`git diff --cached --name-only --diff-filter=ACM`），跑 `ruff check` 然后 `mypy app/ scripts/ --ignore-missing-imports`。无 Python 暂存则提前退出。

### `commit-msg`

强制 Conventional Commits。正则：

```
^(feat|fix|docs|style|refactor|perf|test|chore|revert)(\([a-zA-Z0-9._/-]+\))?: .{2,100}$
```

拒绝以句号结尾的 subject。失败时打印期望格式与示例。

## 本地 CI 等价

```bash
make ci-local
```

聚合（[`Makefile:57-58`](../../Makefile)）：`lint typecheck test-backend test-frontend test-e2e boundary execution-ownership projection-provenance conversation-rebuild export-roundtrip-verify`。完成打印「ci-local checks passed」。

## Windows 支持

[`Makefile.ps1`](../../Makefile.ps1) 是 PowerShell 等价，`switch` on `$Task`。提供子集：`help`、`install`、`install-hooks`、`dev`（手动两终端）、`test-backend`、`test-frontend`、`lint`、`typecheck`、`boundary`、`docker-up`、`docker-down`。

注意：typecheck 的 agents 文件列表与 Unix Makefile 略有差异（`planner.py`/`critic.py`/`llm_router.py` vs `llm_failover.py`/`conversation.py`/`memory_engine.py`/`memory_extractor.py`），且包含 `app/product/`、`app/api/`、`app/main.py`。未知任务报错。

## 密钥扫描

[`.gitleaks.toml`](../../.gitleaks.toml) 扩展默认规则集，两个 allowlist：

1. `.env.example`、`docs/*.md`、`README*.md`、`CONTRIBUTING.md` 中的示例/模板值，加已知占位符（`your-deepseek-api-key`、`your-gmail-app-password`、`your-email@gmail.com`、`sk-test-key`、`demo-seed`）。
2. `backend/tests/` 下的占位符 hash。

本地：`make secrets-scan`。
