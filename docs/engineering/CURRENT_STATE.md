# CURRENT_STATE

> 本文档回答：**项目今天实际上是什么状态？**
>
> **Lifecycle Stage**：**Early Development**（Runtime Governance 基线完成，核心领域 Conversation/Memory/Goals/Inbox/Approvals 已落地）
> **文档角色**：Architecture Ledger——能力清单、成熟度评级与维护协议的权威来源。
>
> **权威来源**：描述「系统今天是什么」时，**以本文档为准**。
> 如有冲突，以本文 + 代码 + 测试 + CI 为准。
>
> 目标愿景见 [NORTH_STAR.md](NORTH_STAR.md)，不可破坏规则见 [INVARIANTS.md](INVARIANTS.md)，
> 架构总览见 [ARCHITECTURE](../architecture/ARCHITECTURE.md)，未来方向见 [ROADMAP](../product/ROADMAP.md)，
> 已完成里程碑见 [HISTORY.md](HISTORY.md)。

---

## 1. 当前系统概要

### 1.1 技术栈

| 层 | 技术 | 证据 |
|----|------|------|
| 后端 | Python 3.12、FastAPI、uvicorn | `backend/app/main.py` |
| 前端 | Node 20、Vite、React | `frontend/` |
| 主存储 | SQLite（WAL、外键） | `backend/app/store/database.py:22-25` |
| 向量 | ChromaDB PersistentClient | `backend/app/store/vector.py:33-37` |
| Schema | Alembic（生产路径）或 raw DDL（测试） | `backend/app/store/schema_init.py:49-62` |
| LLM | OpenAI 兼容 API（默认 DeepSeek） | `backend/app/config.py` |

### 1.2 进程与部署形态

- **单进程 FastAPI 应用**：启动时初始化 Kernel、Scheduler、TimerEngine、BackgroundWorker、MCP Mesh 等。
- **本地优先**：默认 `HOST=127.0.0.1`；可选 Docker Compose、Electron 桌面壳。
- **非分布式**：无多节点、无服务网格。

### 1.3 表分类

| 类别 | 数量 | 含义 | 示例 |
|------|------|------|------|
| **GOVERNED** | 16 表 | 仅 Kernel 写入，经 Event Log 投影 | event_log, goals, memories, approvals, messages |
| **APP_STORAGE** | 9 表 | 允许应用直写，有审计覆盖 | inbox_emails, llm_calls, tool_calls |

---

## 2. 已实现能力

### 2.1 Kernel 与事件溯源

| 能力 | 证据 |
|------|------|
| Event Log append-only（DB trigger 强制） | `kernel/kernel.py` EVENT_LOG_SCHEMA + triggers |
| emit_event 唯一写入口，同事务投影 | `kernel.emit_event` → projectors |
| 投影注册与 rebuild（12 表字节级一致） | `projectors_registry.py`, `kernel_sovereignty.rebuild` |
| export / import 事件流往返 | `SovereigntyMixin`，CI `verify_export_roundtrip.py` |
| Shadow compare（热路径 0 mismatch） | `execution_shadow_compare.py` |
| 事件驱动恢复 | `test_execution_recovery.py` |

### 2.2 Execution 模型

| 能力 | 证据 |
|------|------|
| Execution 事件流（8 种事件） | `projectors_execution.py`, `constants.py` |
| WorkItem + Scheduler | `work_item.py`, `agent_scheduler.py` |
| ExecutionContext 传给 handler | `execution_context.py`, `test_execution_context.py` |
| Principal + IdentityResolver | `principal.py`, `identity_resolver.py` |
| execution_id → capability caused_by | `kernel.py:621` |

### 2.3 Capability 与治理

| 能力 | 证据 |
|------|------|
| CapabilityGateway 四门授权 | `capability_decision.py` |
| Policy / Grant 事件溯源 | `projectors_governance.py`, `capability_policy.py` |
| Approval 流程（绑定参数、不可重放） | `approval_engine.py` |
| Taint 污点升级 | `taint.py`, `test_taint.py` |
| 内置 MCP 工具（含全部覆盖 CI 校验） | `mcp_hub.py`，CI MCP tools step |
| 外部 MCP Mesh | `mcp_mesh.py`, `mcp_lifecycle.py` |
| Egress 审计（非脱敏） | `egress_gate.py` |

### 2.4 Agent 子系统

| 组件 | 角色 |
|------|------|
| AgentDefinition / AgentInstance | persona + 订阅缓存 |
| AgentRegistry / AgentBus | spawn/kill + 订阅路由 |
| HandlerRegistry + @subscribe | 事件类型 → handler |
| AgentManager | Planner→Worker 流水线（单轨） |

### 2.5 定时与后台

| 组件 | 职责 | 写路径 |
|------|------|--------|
| timer_engine.py | cron/延迟，TimerFired → Execution | Kernel 事件 |
| scheduler_v2.py | 12 个 cron 计划注册 | 经 TimerEngine |
| trigger_engine.py | 条件触发、建议通知 | 直写 triggers（APP_STORAGE），读 event_log |
| background_worker.py | 长任务轮询 | 直写 background_tasks（APP_STORAGE） |

### 2.6 API 与产品功能

| 路由组 | 主要能力 |
|--------|----------|
| chat | 对话 SSE、对话内审批 resolve |
| goals | 目标、子任务（actions）、停滞检测 |
| tasks | 任务树、状态机 |
| tasks/background | 后台任务队列 |
| memory | 记忆 CRUD、语义搜索、用户画像、记忆图谱 |
| approvals | 列出 / 批准 / 拒绝 |
| dashboard | 仪表盘概览 |
| inbox | 邮件轮询、摘要、状态更新 |
| telemetry | LLM 成本、工具统计、健康快照 |
| system | 健康、export / import / destroy、MCP 状态 |
| settings | LLM / Email 配置与连接测试 |
| connectors | 外部连接器（如 calendar） |
| notifications | 通知列表、已读标记 |
| triggers | 触发器定义与评估 |
| `/ws` | WebSocket 实时通知 |

> 路由组随版本演进会增删；权威清单以 Swagger UI (`/docs`) 与 `backend/app/api/` 为准。

### 2.7 认知管线（Pattern → Belief）

- **Pattern Aggregator**：scheduler 触发，`pattern/aggregators.py`
- **Belief Engine**：只读投影，emit BeliefFormed，`belief_engine.py`
- Pattern/Belief/Vector rebuild + quality/survival/idempotency 全部进 CI

### 2.8 领域治理（Domain Governance）

| 领域 | CI 守卫 | 证据 |
|------|---------|------|
| Conversation | messages 行级 `source_event_id` + rebuild | `verify_conversation_rebuild.py` |
| Memory | 生命周期 + provenance | `verify_memory_lifecycle.py` |
| Goals | `parent_id` / action provenance + rebuild | `verify_goal_rebuild.py` |
| Inbox | InboxEmailRecorded 审计链 + provenance | `verify_inbox_audit.py` |

### 2.9 测试覆盖

- `backend/tests/runtime/` 与 `backend/tests/integration/`：覆盖 event sourcing、execution、capability、taint、boundary、agent、coverage、approval flow、dashboard、trigger、settings 等
- Runtime 模块 CI 要求 coverage ≥84%（见 `.github/workflows/ci.yml` `--fail-under=84`）
- 后端测试规模与通过数：以本机实测为准，运行 `cd backend && python3 -m pytest -m "not live_llm" --collect-only -q | tail -1`（测试数随版本演进，不在此硬编码）
- 前端：Vitest 单元测试 + Playwright E2E（`frontend/e2e/chat-approval.spec.ts`，CI 阻断）

---

## 3. 架构成熟度

> 回答「成熟到什么程度」，基于能力、CI 守护与生产路径的综合判断。

| 领域 | 成熟度 | 依据 |
|------|--------|------|
| Event Sourcing（真相层） | **Strong + SSOT** | append-only + rebuild CI；生产路径零 INSERT INTO events |
| Projection Rebuild | **Strong** | 12 表 byte-identical 验证 |
| Sovereignty Export/Import | **Strong** | 往返 CI 验证 |
| Execution Runtime | **Strong** | 事件流、shadow compare、恢复、execution_id 执法 |
| Capability Governance | **Strong** | Gateway、taint、approval、boundary CI；Policy 事件溯源 |
| Agent Runtime | **Stable** | AgentManager 单轨；AgentBus + Scheduler + WorkItem |
| Cognitive Pipeline | **Strong+** | Pattern/Belief/Vector 全 CI；quality/survival/idempotency 守卫 |
| Multi-Agent Isolation | **Strong** | 并发 taint 隔离、WorkItem actor 隔离、contextvars 协程隔离 |
| Causal Provenance | **Strong** | INV-P1 运行时执法 + INV-P7 join 门禁（goals/approvals/handler_executions）；messages 行级 provenance；conversation/goals/memory/inbox 领域 rebuild/audit CI |
| Distributed / Multi-tenant | **Not Started** | North Star NG1/NG4 非目标 |

**阶段判断**：Runtime Governance 基线完成，核心产品域（Conversation/Memory/Goals/Inbox/Approvals）已落地。
当前重点：**缩短首次价值路径，打磨核心体验**。

---

## 4. Ledger 维护协议

> 防止 Ledger 与代码、测试、CI 分叉。

### 4.1 何时必须更新本文

| 触发事件 | 必须更新的章节 |
|----------|----------------|
| 新增能力或移除能力 | §2 表 |
| 架构成熟度显著变化 | §3 表 |
| 新增 APP_STORAGE 直写或绕过 Execution 的路径 | §3 成熟度（降级）；同步 ROADMAP（见 [ROADMAP](../product/ROADMAP.md)） |
| 新增 verify/check 脚本进 CI 或移除 | 同步 ARCHITECTURE.md §9（见 [ARCHITECTURE](../architecture/ARCHITECTURE.md)） |
| 仅产品功能、无治理边界变化 | **不必**改本文 |

### 4.2 谁维护、如何评审

- **作者**：任何改动 Runtime / 存储 / CI 边界 PR 的提交者
- **评审**：PR reviewer 检查 Ledger 项是否随代码更新
- **禁止**：在 README / ADR 中更新「当前状态」——只能改本文

### 4.3 防漂移机制

| 机制 | 状态 |
|------|------|
| PR 模板勾选 | 建议：「是否触及治理边界？若是，已更新 CURRENT_STATE」 |
| `check_boundary` / ownership CI | 已有——代码侧执法 |
| 定期 Ledger 审计 | 建议：每季度对照代码 grep 复核 |

**原则**：CI 守护代码真相；**人工 + PR 规则**守护 Ledger 真相。

### 4.4 文档变更频率预期

| 文档 | 预期频率 |
|------|----------|
| NORTH_STAR | 极少（宪法修订需新版本号） |
| INVARIANTS | 低（Tier 升降、新 INV） |
| HISTORY | 极少（归档已完成的里程碑） |
| ARCHITECTURE | 低（架构变更时更新） |
| GOVERNANCE | 中（治理机制演进） |
| ROADMAP | 中（任务推进） |
| **CURRENT_STATE** | **高**（能力与成熟度随开发推移） |

维护 CURRENT_STATE 不是「文档工作」，而是 **架构治理的一部分**。
