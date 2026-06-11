# 5 分钟上手 · Personal AI Runtime

面向第一次跑起来的用户：最小配置 → 启动 → 验证 → 导出自己的数据。

## 1. 前置条件

- **Python 3.12+**
- **Node.js 20+**
- 一个 **OpenAI 兼容 API Key**（默认配置为 DeepSeek）

可选：Docker & Docker Compose（容器化启动）

## 2. 最小环境变量

在项目根目录：

```bash
cp .env.example .env
```

编辑 `.env`，**至少**设置：

```env
LLM_API_KEY=你的-api-key
```

其余可保持默认。数据默认落在 `backend/data/`（SQLite + Chroma 向量目录）。

> 实验特性（Trajectory / Meaning）默认关闭，无需额外配置。若要开启轨迹 API：`EXPERIMENTAL_TRAJECTORY_ENABLED=true`（需重启后端）。

## 3. 启动（二选一）

### 方式 A：Makefile（推荐）

```bash
make install   # 首次：安装 backend + frontend 依赖
make dev       # 后端 :8000 + 前端 :5173
```

浏览器打开 **http://localhost:5173**

### 方式 B：Docker Compose

```bash
docker compose up --build
```

- 前端：http://localhost:5173  
- 后端 API：http://localhost:8000  
- Swagger：http://localhost:8000/docs  

Compose 文件位于项目根目录 [`docker-compose.yml`](../docker-compose.yml)，与 [README](../README.md) 描述一致。

## 4. 快速验证

1. 打开前端，点击「新对话」，发一条消息 — 应收到 AI 回复。  
2. 健康检查：

```bash
curl http://localhost:8000/api/system/health
```

应返回 `{"status":"ok",...}`。

## 5. 一键导出个人数据

导出包含完整 `event_log`、对话与消息的 JSON 快照（v2.0 无损格式）：

```bash
curl -X POST http://localhost:8000/api/system/export -o my-personal-ai-backup.json
```

或在 Swagger UI（`/docs`）中调用 `POST /api/system/export`。

导入为破坏性写操作，需显式确认码，见 API 文档 `POST /api/system/import`。

## 6. 可选：本地数据一致性检查

SQLite 记忆投影与 Chroma 索引应对齐。自检（隔离环境，不修改你的数据）：

```bash
make vector-consistency-verify
```

检查当前 `backend/data/` 中的真实数据：

```bash
cd backend && python3 scripts/verify_vector_consistency.py --check-default
```

## 7. 下一步

- 参与用户验证与留存指标：见 [USER_VALIDATION.md](USER_VALIDATION.md)  
- 架构与契约：[RUNTIME_SPEC.md](RUNTIME_SPEC.md) · [docs/README.md](README.md)  
- 常见问题：[README § 常见问题](../README.md#常见问题)

---

**预计耗时：** 复制 `.env` + 填 Key ≈ 1 分钟；`make install` 首次 ≈ 2–3 分钟；`make dev` 启动 ≈ 30 秒。
