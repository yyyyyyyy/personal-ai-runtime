# SDK 边界 — 外部 Agent 接入 Runtime 的最小表面

本文档定义 Personal AI Runtime 作为"个人 AI 数据/治理层"被外部 agent（Cursor、Claude Desktop、任意 IDE agent）接入时的**公共 API 表面**。

## 目的

Runtime 的核心价值（event_log + capability_governance + encrypted_sync）不仅服务本项目的前端，也应能被其他 agent 复用——让用户的记忆、审批历史、数据主权跨 agent 共享。

但**不提前做 SDK 包**。本文档只画线：哪些端点是 `@public`（承诺稳定、外部可依赖），哪些是 `@internal`（实现细节，随时可变）。真正的 SDK 拆包等 Phase 3.2 的 dogfood 验证后再做。

---

## @public 端点（外部 agent 可依赖）

这 5 个能力构成"个人 AI 数据/治理层"的最小契约：

| 能力 | HTTP 端点 | 用途 |
|---|---|---|
| **recall_unified** | `GET /api/memory/memories/search?q=` + `POST /api/knowledge/search` | "用户已知什么"——跨记忆+文档的语义检索 |
| **store_memory** | `POST /api/memory/memories` | "记住这件事"——写入长期记忆（经 Kernel 事件溯源） |
| **invoke_capability** | （经 SSE chat 流，或未来的 `/api/capabilities/invoke`） | "做这个操作"——受 4-gate 治理的工具调用 |
| **emit_event** | （Kernel ABI，非 HTTP） | "记录这个事实"——写入不可变事件日志 |
| **subscribe_events** | `WS /ws` | "监听变化"——实时事件流（记忆更新、审批请求、通知） |

### 稳定性承诺

- `@public` 端点的**请求/响应结构**是契约，破坏性变更需 deprecation 周期。
- `@public` 端点的**语义**（"store_memory 一定经过 Kernel 事件溯源"）是不可违反的不变量。
- 内部重构（如 recall_unified 从 Kernel 移到 read_ports）**不影响** @public 地位，只要端点行为不变。

---

## @internal 端点（实现细节）

以下端点为**本项目前端专用**，外部 agent 不应依赖：

- `/api/goals/*`、`/api/work-items/*`、`/api/tasks/*`——业务投影，结构随 WorkItem 演进变化
- `/api/dashboard`、`/api/timeline/events`——UI 聚合，实现细节
- `/api/telemetry/*`——监控用，结构可变
- `/api/inbox/*`、`/api/connectors/*`——集成层，依赖外部服务
- `/api/system/data`（导出）、`/api/system/import`、`/api/system/destroy`——数据主权操作，仅本人可用

---

## 验证计划（Phase 3.2）

写一个 MCP server，暴露 `@public` 能力给 Cursor。如果作者自己日常用 Cursor + 本项目 memory 觉得"比纯 Cursor 好"，证明 SDK 边界正确；如果不用，说明边界画错了或价值不成立，重新评估。

**不在 Phase 3.1 做的事**：不拆 Python 包、不发 PyPI、不写 TypeScript SDK。只画线 + 标注 + CI check。

---

## CI 守卫（待实现）

`backend/scripts/check_sdk_boundary.py` 将断言：
1. `@public` 端点有显式 docstring 标注 `@public`
2. `@public` 端点的响应结构有对应 TypeScript 类型（前端 types.ts）
3. 任何 `@public` 端点的删除/重命名需同时更新本文档表格
