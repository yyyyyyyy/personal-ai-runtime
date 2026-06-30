# API 参考

后端基于 **FastAPI**，自动生成 OpenAPI 规范。

## 交互式文档（权威来源）

启动后端后访问：

- **Swagger UI**：`http://localhost:8000/docs`
- **ReDoc**：`http://localhost:8000/redoc`
- **OpenAPI JSON**：`http://localhost:8000/openapi.json`

Swagger UI 与代码 100% 同步，是端点详情的权威来源。本文档列出路由总览和常用 curl 示例。

---

## 路由组总览（16 个活跃路由组 + WebSocket）

| 路由前缀 | 职责 |
|---------|------|
| `/api/chat` | 对话、消息（SSE 流式）、对话内审批 resolve |
| `/api/goals` | 目标、子任务（actions）、停滞检测 |
| `/api/tasks` | 任务树、状态机 + 后台任务 (`/api/tasks/background`) |
| `/api/memory` | 记忆 CRUD、语义搜索、用户画像（portrait） |
| `/api/inbox` | 邮件轮询、摘要、状态更新 |
| `/api/approvals` | 审批列表、approve / reject |
| `/api/dashboard` | 仪表盘概览 |
| `/api/telemetry` | LLM 成本、工具调用统计 |
| `/api/system` | 健康检查 (health/live/ready)、export / import / destroy、MCP 状态 |
| `/api/settings` | LLM / Email 配置与连接测试 |
| `/api/connectors` | 外部连接器注册与管理 |
| `/api/notifications` | 通知列表、已读标记 |
| `/api/triggers` | 触发器定义与评估 |
| `/api/knowledge` | 知识库文档上传与搜索 |
| `/api/timeline` | 事件时间线 |
| `/api/workflows` | ⚠️ **DEPRECATED**（实验分支：已于 v0.2 降级，API 不稳定，计划 v0.3/v0.7 移除） |
| `/ws` | WebSocket 实时通知 |

**总计**: 16 个活跃路由组 + 1 个废弃路由组 + WebSocket

---

## 认证

API 认证可选。若在 `.env` 中设置了 `AUTH_TOKEN`，所有 HTTP 请求需携带：

```
Authorization: Bearer <AUTH_TOKEN>
```

**AuthMiddleware** 直接实现为纯 ASGI 中间件（非 BaseHTTPMiddleware），以支持 SSE 流式响应不被缓冲。

**白名单路径** (无需认证，6 个):

| 路径 | 说明 |
|------|------|
| `/` | 根路径 |
| `/api/system/health` | 健康检查 |
| `/api/system/live` | 存活探针 |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI Schema |

WebSocket 客户端在 `Sec-WebSocket-Protocol` 中发送 `auth.<token>` 与 `auth.ok`；服务端校验后仅协商 `auth.ok`（不回显 token）。未设置 `AUTH_TOKEN` 时，默认仅绑定 `127.0.0.1` 且不鉴权。

---

## SSE 事件流

Chat 消息发送返回 **Server-Sent Events (SSE)** 流。事件类型：

| 事件类型 | 含义 | 是否持久化到 event_log |
|----------|------|------------------------|
| `text_delta` | 逐字符文本增量 | **否** — 通过内存 SSE 队列传递（不污染真相层） |
| `tool_call_start` | 工具调用开始 | 否 |
| `tool_result` | 工具调用结果 | 否 |
| `confirmation_required` | 需要用户确认审批 | 是 (ApprovalRequested) |
| `done` | 对话完成 | 是 (ChatCompleted + ChatDone) |

---

## 常用 curl 示例

### 健康检查

```bash
curl http://localhost:8000/api/system/health
```

### 创建对话并发送消息

```bash
# 1. 创建对话
curl -X POST http://localhost:8000/api/chat/conversations \
  -H "Content-Type: application/json" \
  -d '{"title": "我的第一个对话"}'

# 2. 发送消息（SSE 流式响应）
curl -N -X POST http://localhost:8000/api/chat/conversations/<conversation_id>/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "帮我查询今天的邮件"}'
```

### 创建目标

```bash
curl -X POST http://localhost:8000/api/goals/ \
  -H "Content-Type: application/json" \
  -d '{"title": "完成周报", "priority": "high", "description": "本周工作总结"}'
```

### 审批操作

```bash
# 列出待审批
curl http://localhost:8000/api/approvals/?pending_only=true

# 批准
curl -X POST http://localhost:8000/api/approvals/<approval_id>/approve

# 拒绝
curl -X POST http://localhost:8000/api/approvals/<approval_id>/reject
```

### 数据主权（导出/导入）

```bash
# 导出全部个人数据（需确认码）
curl -X POST http://localhost:8000/api/system/export \
  -H "Content-Type: application/json" \
  -d '{"confirm":"EXPORT_ALL_DATA"}' \
  -o backup.json

# 破坏性导入（需确认码）
curl -X POST http://localhost:8000/api/system/import \
  -H "Content-Type: application/json" \
  -d '{"read_only":false,"confirm":"DESTROY_AND_IMPORT","data":{...}}'
```

### 遥测

```bash
# 工具调用统计
curl http://localhost:8000/api/telemetry/tool-calls?limit=20

# 工具调用摘要
curl http://localhost:8000/api/telemetry/tool-summary
```

---

## 更多

- 用户手册：[USER_GUIDE](../guides/USER_GUIDE.md)
- 开发者指南：[DEVELOPER_GUIDE](../guides/DEVELOPER_GUIDE.md)
- 环境变量：[CONFIGURATION](CONFIGURATION.md)
- 架构概述：[ARCHITECTURE](../architecture/ARCHITECTURE.md)
- 交互式文档：启动后端后访问 `http://localhost:8000/docs`
