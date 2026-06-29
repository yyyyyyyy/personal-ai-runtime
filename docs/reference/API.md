# API 参考

后端基于 **FastAPI**，自动生成 OpenAPI 规范。

## 交互式文档（权威来源）

启动后端后访问：

- **Swagger UI**：`http://localhost:8000/docs`
- **ReDoc**：`http://localhost:8000/redoc`
- **OpenAPI JSON**：`http://localhost:8000/openapi.json`

Swagger UI 与代码 100% 同步，是端点详情的权威来源。本文档列出路由总览和常用 curl 示例。

---

## 路由组总览

| 路由前缀 | 职责 |
|---------|------|
| `/api/chat` | 对话、消息（SSE 流式）、对话内审批 resolve |
| `/api/goals` | 目标、子任务（actions）、停滞检测 |
| `/api/tasks` | 任务树、状态机 |
| `/api/tasks/background` | 后台任务队列 |
| `/api/memory` | 记忆 CRUD、语义搜索、用户画像、记忆图谱 |
| `/api/inbox` | 邮件轮询、摘要、状态更新 |
| `/api/approvals` | 审批列表、approve / reject |
| `/api/dashboard` | 仪表盘概览 |
| `/api/telemetry` | LLM 成本、工具统计、健康快照 |
| `/api/system` | 健康、export / import / destroy、MCP 状态 |
| `/api/settings` | LLM / Email 配置与连接测试 |
| `/api/connectors` | 外部连接器（如 calendar） |
| `/api/notifications` | 通知列表、已读标记 |
| `/api/triggers` | 触发器定义与评估 |
| `/api/knowledge` | 知识库文档上传与搜索 |
| `/api/timeline` | 事件时间线 |
| `/api/workflows` | 工作流管理 |
| `/ws` | WebSocket 实时通知 |

---

## 认证

API 认证可选。若在 `.env` 中设置了 `AUTH_TOKEN`，所有 HTTP 请求需携带：

```
Authorization: Bearer <AUTH_TOKEN>
```

WebSocket 客户端在 `Sec-WebSocket-Protocol` 中发送 `auth.<token>` 与 `auth.ok`；服务端校验后仅协商 `auth.ok`（不回显 token）。未设置 `AUTH_TOKEN` 时，默认仅绑定 `127.0.0.1` 且不鉴权。

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

响应为 **Server-Sent Events (SSE)** 流，事件类型包括 `text_delta`、`tool_call_start`、`tool_result`、`confirmation_required`、`done`。

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

# 导入校验（只读）
curl -X POST http://localhost:8000/api/system/import \
  -H "Content-Type: application/json" \
  -d '{"read_only":true,"data":{...}}'

# 破坏性导入（需确认码）
curl -X POST http://localhost:8000/api/system/import \
  -H "Content-Type: application/json" \
  -d '{"read_only":false,"confirm":"DESTROY_AND_IMPORT","data":{...}}'
```

---

## 更多

- 用户手册：[USER_GUIDE](../guides/USER_GUIDE.md)
- 开发者指南：[DEVELOPER_GUIDE](../guides/DEVELOPER_GUIDE.md)
- 环境变量：[CONFIGURATION](CONFIGURATION.md)
- 交互式文档：启动后端后访问 `http://localhost:8000/docs`
