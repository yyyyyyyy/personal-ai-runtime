# 部署

本文档描述 Docker Compose、单容器构建与桌面端打包。

## Docker Compose（推荐生产方式）

[`docker-compose.yml`](../../docker-compose.yml) 定义两个 service：

### backend

```yaml
build: { context: ., dockerfile: backend/Dockerfile }
ports: ["127.0.0.1:8000:8000"]
env_file: [.env]
environment:
  - HOST=0.0.0.0                          # 覆盖默认 localhost-only
  - AUTH_TOKEN=${AUTH_TOKEN:-}             # 生产必需
volumes: [backend-data:/app/backend/data]  # 命名卷
working_dir: /app/backend
command: python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/system/live"]
  interval: 10s, timeout: 5s, retries: 5, start_period: 15s
```

端口绑 `127.0.0.1:8000:8000`（仅本机）。`AUTH_TOKEN` 注释明确警告生产必需。

### frontend

```yaml
build:
  context: .
  dockerfile: frontend/Dockerfile
  args: { VITE_API_HOST: backend, VITE_API_PORT: "8000" }
ports: ["5173:5173"]
environment: [VITE_API_HOST=backend, VITE_API_PORT=8000]
working_dir: /app/frontend
command: npx serve dist -l 5173 --no-clipboard
depends_on: { backend: { condition: service_healthy } }
```

构建时注入 `VITE_API_HOST=backend`（Docker 内部网络主机名）。等 backend 健康后才启动。

### 卷

`backend-data` 命名卷挂到 `/app/backend/data`，持久化 SQLite 与 ChromaDB。

### 操作

```bash
make docker-up      # docker compose up --build
make docker-down    # docker compose down
```

## 单容器 Dockerfile

### `backend/Dockerfile`

- 基础镜像 `python:3.12-slim`。
- 装 `build-essential` + `curl`。
- `pip install -r requirements.txt`。
- 复制 backend。
- `PYTHONPATH=/app/backend`、`DATA_DIR=/app/backend/data`。
- 创建非 root `par` 用户（uid 1000）。
- 暴露 8000。
- 运行 uvicorn。

### `frontend/Dockerfile`

两阶段：

- **builder**：接受构建参数 `VITE_API_HOST`/`VITE_API_PORT`，`npm ci` + `npm run build`。
- **runtime**：复制 `dist`、`package.json`、`vite.config.ts`、`node_modules`，`npx vite preview` 服务于 5173。

## 桌面端打包

```bash
make desktop-build   # cd desktop && npm run build  (electron-builder)
```

[`desktop/package.json`](../../desktop/package.json) 的 electron-builder 配置：

- `appId: com.personalairuntime.desktop`、`productName: Personal AI Runtime`。
- `files`：`main.js`、`preload.js`、`icon.png`、`generate_icon.py`。
- `extraResources`：把整个 `../backend` bundle 为 `backend`（排除 `__pycache__`、`*.pyc`、`data/**`）。**打包发行版包含 Python 源码，但运行时仍需系统 Python 3**（`main.js` spawn `python3`）。
- Targets：
  - macOS：`dmg`、`zip`（category `public.app-category.productivity`）
  - Windows：`nsis`、`portable`
  - Linux：`AppImage`、`deb`（category `Office`）
- `postinstall`：`python3 generate_icon.py` 生成 `icon.png`。

> 前端构建产物通过 [`desktop/prebuild.js`](../../desktop/prebuild.js) 在 `npm run prebuild` 阶段复制到 `desktop/frontend-dist/`，并在 electron-builder 配置的 `files` 中以 `"frontend-dist/**/*"` 显式嵌入（见 [`desktop/package.json`](../../desktop/package.json)）。打包后 `main.js` 通过 `app://` 协议加载本地前端，生产模式无需独立前端服务。

## 发布

GitHub Release 由 [`workflows/release.yml`](../../.github/workflows/release.yml) 在 `v*.*.*` tag 时创建（详见 [ci-cd.md](ci-cd.md)）。当前未见自动上传桌面端构建产物到 Release 的工作流配置——代码库中证据不足。

## 数据持久化

| 部署方式 | SQLite 路径 | ChromaDB 路径 |
|---|---|---|
| 本地开发 | `<repo>/backend/data/personal_ai.db` | `<repo>/backend/data/vectors/` |
| Docker Compose | `/app/backend/data/personal_ai.db`（卷 `backend-data`） | `/app/backend/data/vectors/`（同卷） |
| 桌面打包 | 由系统 `DATA_DIR` 决定 | 同 |

数据可经 `POST /api/system/export`（明文 JSON）或 `POST /api/system/export/encrypted`（AES-GCM + PBKDF2，base64）导出；经 `POST /api/system/import` 或 `/import/encrypted` 导入；`DELETE /api/system/data`（body `{"confirm": "DESTROY_ALL_DATA"}`；若已配置 `AUTH_TOKEN` 则同时需要 Bearer）不可逆销毁。详见 [03-subsystems/backend-api.md](../03-subsystems/backend-api.md) 与 [04-data/data-model.md](../04-data/data-model.md)。

## 生产安全清单

1. 设 `AUTH_TOKEN`（强随机值）。
2. `ALLOW_NO_AUTH_ON_EXPOSED` 保持 `False`（默认）。
3. 端口绑 `127.0.0.1`（Docker Compose 已默认；裸 uvicorn 默认也是 localhost）。
4. 若必须暴露公网，前置反向代理 + TLS。
5. 定期 `POST /api/system/export/encrypted` 备份。
6. `make secrets-scan` 确认无泄漏。

详见 [security.md](security.md)。
