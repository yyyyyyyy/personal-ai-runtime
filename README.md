# Personal AI OS

本地优先的个人 AI 运行时：带上下文的对话、目标管理、记忆沉淀、工具执行与审批治理。

## 环境要求

- Python 3.12+
- Node.js 20+
- （可选）Ollama — 本地记忆抽取与敏感操作路由
- （可选）Docker & Docker Compose — 容器化启动

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少设置 LLM_API_KEY（DeepSeek 等 OpenAI 兼容 API）
```

### 2. 方式 A：Makefile（推荐日常开发）

```bash
make install   # 安装 backend + frontend 依赖
make dev       # 并行启动后端 (8000) 与前端 (5173)
```

浏览器打开 http://localhost:5173

### 3. 方式 B：Docker Compose

```bash
docker compose up --build
```

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

### 4. 桌面端（可选）

```bash
make desktop
# 或
cd desktop && npm install && npm start
```

Electron 壳会通过 WebSocket (`ws://localhost:8000/ws`) 接收桌面通知。

## 手动启动

```bash
# 后端 — 必须在 backend/ 目录下运行
cd backend
python3 -m uvicorn app.main:app --reload --port 8000

# 前端（新终端）
cd frontend
npm run dev
```

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | 主 LLM API Key（必填） | — |
| `LLM_BASE_URL` | API 地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `OLLAMA_BASE_URL` | 本地 Ollama（记忆抽取） | `http://localhost:11434/v1` |
| `MEMORY_EXTRACTOR` | 记忆抽取后端：`ollama` 或 `cloud` | `ollama` |
| `CORS_ORIGINS` | 允许的前端源 | `http://localhost:5173,http://localhost:5174` |
| `MCP_CONFIG_PATH` | 外部 MCP 服务器配置 | `./backend/mcp_config.json` |

完整列表见 [.env.example](.env.example)。

## 常用命令

```bash
make test          # backend pytest + frontend tsc
make test-backend  # 仅后端测试
make test-frontend # 仅前端类型检查
make boundary      # Kernel 边界守卫检查
make rebuild-verify # Event Log 重建验证
```

## 功能概览

| 页面 | 能力 |
|------|------|
| Chat | 带记忆/目标上下文的对话，工具调用，高风险操作审批 |
| Goals | 目标与行动管理，停滞检测 |
| Dashboard | 系统状态与主动建议 |
| Timeline | 活动与事件时间线 |

## 测试审批流程

1. 在对话中让 AI 执行写文件等高风险操作（如「在桌面创建一个 test.txt」）
2. 前端弹出确认对话框
3. 点击「批准」后工具执行；点击「拒绝」则 AI 收到拒绝反馈

## 数据主权

```bash
# 导出全部个人数据
curl -X POST http://localhost:8000/api/system/export -o backup.json

# 导入（需确认码，见 API 文档）
curl -X POST http://localhost:8000/api/system/import -d '{"confirm":"DESTROY_AND_IMPORT","data":{...}}'
```

## 常见问题

**`ModuleNotFoundError: No module named 'app'`**  
必须在 `backend/` 目录下启动 uvicorn，不要在 `backend/backend/` 或其他路径。

**前端连不上后端 / CORS 错误**  
若 Vite 使用了 5174 端口，确保 `.env` 中 `CORS_ORIGINS` 包含 `http://localhost:5174`。

**对话一直「思考中」**  
检查 `LLM_API_KEY` 是否有效，查看后端终端错误日志。

**ChromaDB 首次启动慢**  
首次运行会下载 embedding 模型，属正常现象。

## 架构

```
User → Runtime Kernel (Event Log / State / Permissions)
         ├─ Agents (Brain, Planner, Critic — ephemeral)
         ├─ Capabilities (MCP Tools)
         └─ Storage (SQLite + ChromaDB, 本地)
```

架构契约详见 [RUNTIME_SPEC.md](RUNTIME_SPEC.md)。

## 版本

当前版本：**0.9.0**（backend / frontend / desktop 统一）
