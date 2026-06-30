# ARCHITECTURE

> 本文档解释 Personal AI Runtime 的运行时架构。
> 它回答"系统如何工作"，不回答"系统应该做什么"（见 CONSTITUTION.md）。
> 它描述当前架构，不描述未来架构（见 ROADMAP.md）。
>
> **版本：v3.0（基于 Truth Audit 2026-06-30）**
> **FACT 追溯源**: `docs/engineering/TRUTH_AUDIT.md`

---

## 1. 架构概览

Personal AI Runtime 是一个**事件溯源（Event Sourced）的本地 AI 运行时**。其架构分为两个空间：

```
┌──────────────────────────────────────────────────────────────────┐
│  USER SPACE                                                      │
│                                                                  │
│  API Layer (FastAPI routers, 17 route groups)                    │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌────────────────┐    │
│  │  Brain   │ │ TaskEngine │ │ MCPHub   │ │ ContextPipeline│    │
│  │(LLM loop)│ │(Goal/Task) │ │(Tools)   │ │(Fragment→Prompt│    │
│  └────┬─────┘ └─────┬──────┘ └────┬─────┘ └───────┬────────┘    │
│       │              │             │                │             │
│       └──────────────┼─────────────┼────────────────┘             │
│                      │             │                              │
│         ┌────────────┴─────────────┴──────────┐                   │
│         │  Runtime Subsystems                  │                   │
│         │  Scheduler, AgentBus, TimerEngine,   │                   │
│         │  CapabilityGateway, ApprovalEngine,  │                   │
│         │  BackgroundWorker, TriggerEngine      │                   │
│         └────────────┬────────────────────────┘                   │
├──────────────────────┼───────────────────────────────────────────┤
│  KERNEL SPACE        │  唯一访存储的代码                          │
│                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Kernel ABI                             │   │
│  │  emit_event()  query_state()  read_events()             │   │
│  │  invoke_capability()  request_approval()                │   │
│  │  submit_command()                                       │   │
│  └───────────┬──────────────────────────────────────────────┘   │
│              │                                                    │
│    ┌─────────┼──────────┐                                        │
│    │         ▼           │                                        │
│    │   event_log table   │  不可变、只追加                      │
│    │         │           │                                        │
│    │    ┌────▼─────┐     │                                        │
│    │    │Projectors│     │  同步、同事务运行（7 模块）          │
│    │    └────┬─────┘     │                                        │
│    │         ▼           │                                        │
│    │  projection tables  │  goals, actions, tasks,              │
│    │                     │  memories, approvals, conversations, │
│    │                     │  handler_executions, timer_events,   │
│    │                     │  policy_events, grant_events,        │
│    │                     │  notifications (14 GOVERNED)          │
│    └─────────────────────┘                                        │
│    ┌─────────────────────┐                                        │
│    │  ChromaDB (memory)  │  语义索引，两阶段同步                 │
│    │  + knowledge index  │  (emit_event 预计算 + _sync 修复)     │
│    └─────────────────────┘                                        │
│    ┌─────────────────────┐                                        │
│    │  SQLite APP_STORAGE │  user_profile, app_settings,          │
│    │  (direct read/write)│  background_tasks, llm_calls,         │
│    │                     │  tool_calls, triggers, inbox_emails   │
│    └─────────────────────┘                                        │
└──────────────────────────────────────────────────────────────────┘
```

### 核心规则

1. **Kernel Space 是唯一访存储的代码。** User Space 代码通过 Kernel ABI 与存储交互，不可直接读写 GOVERNED 表（FACT-1）。
2. **State = 物化投影。** goals、tasks、memories 等表是事件日志的投影，由 7 个 Projector 模块在事件提交时同步写入（FACT-5）。
3. **Event Log 是唯一真相。** 扔掉所有投影表，都可以从事件日志确定性重建（FACT-5, I-002）。
4. **Capability 经过授权裁决。** 任何工具调用经过 CapabilityGateway 的四门授权检查（FACT-11, I-003）。

---

## 2. 核心概念

### 2.1 Event（事件）

不可变的事实记录。`frozen=True` dataclass。一旦提交，永不修改。

```python
Event(
    seq: int,              # 全局单调序号（日志分配，非时间）
    id: str,               # 唯一事件 ID
    type: str,             # 事件类型，如 GoalCreated, TaskCompleted
    aggregate_type: str,   # 聚合类型，如 "goal", "task"
    aggregate_id: str,     # 聚合实例 ID
    actor: str,            # 触发者：user / agent:xxx / system / scheduler
    payload: dict,         # 事件荷载
    caused_by: str | None, # 直接前驱事件 ID（因果链）
    correlation_id: str,   # 一次意图的所有事件共享的 trace id
    ts: str,               # 墙钟时间（仅展示用；排序用 seq）
)
```

### 2.2 Kernel

Runtime 的核心。`Kernel` 通过 Mixin 组合（多重继承）四个职责（B-001）：

| Mixin | 职责 |
|---|---|
| `Kernel` (本体) | `emit_event()` — 唯一写入口。事务中写 event_log + 运行 Projectors + dispatch |
| `QueryStateMixin` | `query_state()` — 从投影表读取状态（12 个 _query_* 方法）|
| `GovernanceMixin` | `request_approval() / grant_approval() / deny_approval()` — 审批生命周期 |
| `SovereigntyMixin` | `export_data() / import_data() / rebuild()` — 数据主权 |

Kernel 是全局单例（`kernel_instance.kernel`），通过 `RuntimeContainer` 访问（FACT-3）。

### 2.3 Projector（投影器）

投影器是 Kernel 事务中同步运行的函数，将 Event 转换为投影表的 INSERT/UPDATE/DELETE。7 个投影模块覆盖所有聚合类型（FACT-5）：

| 投影模块 | 聚合类型 |
|---|---|
| `projectors_core.py` | goal, memory, task, action, approval, claim |
| `projectors_chat.py` | conversation |
| `projectors_execution.py` | handler_execution |
| `projectors_governance.py` | policy, grant |
| `projectors_background.py` | background_task |
| `projectors_aux.py` | notification |
| `projectors_timer.py` | timer |

投影器运行在**同一 SQL 事务**内——投影表与事件日志始终一致。

### 2.4 Capability（能力）

Agent 可以调用的外部世界操作（B-003）。分为：

- **Builtin Tools**: 37 个硬编码工具，分属 13 个类别（time, filesystem, web, calendar, email, browser, clipboard_ocr, shell, git, telegram, goals, computer_use, voice）（FACT-27）。
- **External MCP Tools**: 通过 MCP Mesh 动态发现的 stdio 子进程外部工具（FACT-28）。

每个能力有：
- `risk_level`: forbidden / high / low（由 `CapabilityPolicy` 管理，事件溯源）
- `requires_confirmation`: 是否需要用户确认
- `taint_classification`: 外部摄取 6 个工具 + write-class 9 个工具的分类（FACT-30）

### 2.5 Principal（身份主体）

经过类型化的身份标识。三种类型（FACT-11, FACT-18）：

- `user`: 人类用户。享有最高权限。
- `agent:{instance_id}`: AI Agent 实例。受限权限，需显式授权（Grant）。
- `system` / `scheduler` / `background`: 系统内部进程。特定能力豁免。

运行时所有权角色：`agent:*` + `RUNTIME_OWNERSHIP_ACTORS`（scheduler, executor, background）。

### 2.6 Execution（执行记录）

每次 Handler 的执行被记录在 `handler_executions` 表中。包含：

- `execution_id`: 本次执行的唯一标识
- `event_seq`: 触发事件在 event_log 中的 seq
- `status`: pending → running → completed / failed / retrying
- `correlation_id`: 关联的事件链

每个 Capability 调用都携带 `execution_id`，实现完整因果追踪（FACT-18, I-003）。

### 2.7 Approval（审批）

高风险能力调用需要用户审批。审批生命周期（FACT-14, B-002）：

```
ApprovalRequested → ApprovalGranted | ApprovalDenied | ApprovalExpired
```

- "low" 风险 → 自动通过（ApprovalGranted 自动发出）
- "high" 风险 → 等待用户确认
- 非 user 主体 high risk → 自动拒绝
- `BackgroundTaskFailed` 特殊处理：也解析 `BackgroundTaskCompleted` 等待者（FACT-19）

### 2.8 Memory（记忆）

双存储架构：SQLite `memories` 表 + ChromaDB 语义索引（FACT-21, FACT-23）。

写入路径：`MemoryEngine.store_memory()` → `kernel.emit_event("MemoryDerived")` → projector 写 SQLite + ChromaDB 预计算 → `_sync_memory_index` 提交后修复（FACT-22, ADR-2025-003）。

特征：
- 置信度 [0, 1]，初始默认 0.5（FACT-24）
- origin 区分 "self_report"（用户）vs "claim"（AI 推断）
- 衰减通过 cron 每天 3:00 批量运行（FACT-25）
- `user_profile` 表为单独存储，直写 SQLite（FACT-26, ADR-2026-006）

---

## 3. 执行模型

### 3.1 Chat 请求完整流程（5 阶段管线）

FACT-10 描述了从用户消息到响应的完整链路：

```
User Message
    │
    ▼
POST /api/chat → emit_event("ChatRequested")    [Stage 1: API]
    │  + 创建 SSE queue（ChatTextDelta 不写 event_log）
    ▼
Kernel._dispatch() → AgentBus.publish(event)    [Stage 2: Event Dispatch]
    │
    ▼
AgentInstance.dispatch() → Scheduler.enqueue()  [Stage 3: Agent Routing]
    │
    ▼
Scheduler._process_work_item() → on_chat_requested(ctx, event)  [Stage 4: Handler]
    │
    ├─ 1. ContextPipeline.build(user_message)
    │     ├─ QueryAnalyzer.analyze() → tags
    │     ├─ FragmentSelector.select(tags, stage)
    │     ├─ ContextAssembler.assemble(fragments, budget)
    │     └─ → system_prompt (compiled string)
    │
    ├─ 2. Brain.chat_stream(conversation, msg, prompt)
    │     ├─ Build messages [system, history, user]
    │     ├─ LLM API call (streaming, multi-provider failover)
    │     ├─ Collect text deltas → SSE to client
    │     ├─ If tool calls:
    │     │   └─ ToolDispatcher.dispatch(tool_calls)
    │     │       └─ kernel.invoke_capability(name, args)    [Stage 5: Capability]
    │     │           └─ CapabilityGateway.decide()
    │     │               ├─ Gate 1: policy forbidden?
    │     │               ├─ Gate 2: has grant?
    │     │               ├─ Gate 3: pre-approved?
    │     │               └─ Gate 4: risk → approval?
    │     ├─ If approval needed → "confirmation_required"
    │     └─ Update messages with tool results
    │
    ├─ 3. Save assistant message + tool calls
    ├─ 4. Fire-and-forget: memory extraction
    ├─ 5. emit ChatCompleted
    └─ 6. emit ChatDone → push "done" to SSE queue
```

### 3.2 WorkItem 状态机

FACT-7, I-007 描述的执行状态转换：

```
pending → running → completed        (正常完成)
pending → running → failed           → retrying → pending  (重试循环)
running → failed                     (超过最大重试，终止）
```

- Scheduler 每 50ms tick，最多 8 个并发 WorkItem
- 启动时 `_recover()` 恢复 pending/running/retrying 状态的 WorkItem
- 超时的 running WorkItem 自动转为重试

### 3.3 后台循环（三个独立循环）

| 循环 | 频率 | 职责 | Trace |
|---|---|---|---|
| TimerEngine | 1 秒 | 扫描 timer_events，到期则 emit TimerFired；8 个 cron 注册 | FACT-12 |
| BackgroundWorker | 10 秒 | 清理过期 Agent、过期审批、停滞目标检测、执行后台任务 | FACT-13 |
| Scheduler | 50 毫秒 | WorkItem 调度和执行 | FACT-7 |
| TriggerEngine | 30 分钟（cron） | 评估阈值和停滞条件触发器 | — |

### 3.4 submit_command 同步模式

FACT-14: `kernel.submit_command()` 提供请求-响应模式。通过 `asyncio.Future` 键为 `(correlation_id, completion_type)`，等待匹配完成事件。默认超时 60 秒。`BackgroundTaskFailed` 特殊处理：同时解析 `BackgroundTaskCompleted` 等待者。

### 3.5 启动序列

FACT-19 描述了应用启动时 6 个子系统的初始化顺序：

1. `run_startup_checks()` — 健康检查
2. `init_scheduler()` — cron 注册 + timer 初始化
3. `capability_policy.seed_from_json(kernel)` — 策略初始化
4. `await background_worker.start()` — 后台轮询
5. `trigger_engine.seed_builtin_triggers()` — 触发条件注入
6. `await start_mcp_mesh()` — MCP 外部工具发现（失败不阻塞）

---

## 4. 治理模型

### 4.1 能力授权四门模型

`CapabilityGateway.decide()` 执行四门检查（FACT-11, ADR-2025-002）：

**Gate 1 — 策略禁止（forbidden）**
从 `policy_events` 投影读取。如果 `risk_level == "forbidden"`，直接拒绝。

**Gate 2 — 身份授权（grants）**
从 `grant_events` 投影读取。user/system 主体始终通过。agent 主体必须有匹配能力的活跃 Grant（或通配符 `*`）。Fail-closed：无 Grant 即拒绝。

**Gate 3 — 预批准快速通道**
当 `pre_approved=True` 且提供了 `approval_id`，Kernel 验证审批与调用匹配后自动通过。由 `_consume_pre_approved()` 实现。

**Gate 4 — 风险评估 + 审批**
- `sensitive_router.elevated_risk()` + `taint_registry` 评估风险
- 如果 correlation_id 被污点标记（外部不可信内容），且工具是 write-class，风险提升至 "high"
- 非 user 主体无法解决审批 → high risk 自动拒绝
- user 主体触发审批流程（`kernel.request_approval()`）

### 4.2 污点追踪（Taint Tracking）

FACT-30: `TaintRegistry` 使用 `contextvars.ContextVar` 作为 async-safe 存储。6 个工具被分类为"外部摄取"（可引入不可信内容），9 个工具被分类为 "write-class"（可修改系统）。当摄取工具的 taint 传播到 write-class 工具时，风险自动升级至 "high"。

### 4.3 Context 管线

`ContextPipeline` 将用户消息编译为 LLM 的 system prompt：

```
用户消息
  → QueryAnalyzer（分析意图、提取标签）
  → DefaultContextPolicy（选择阶段和策略）
  → FragmentSelector（按 tier 选择 context fragment）
  → ContextAssembler（并发 collect + token 预算管理）
  → PromptCompiler（合并为 system prompt 字符串）
```

Context Fragment 按 tier 分类：
- **Core**: 始终包含（Memory, Goals, World Context）
- **Preference**: 按需包含（Conversation State, Knowledge）
- **Scenario**: 条件触发（Calendar, Mail, Actions, Events）

**已知休眠**: FACT-36: `ExecutionContextProvider` 和 `CapabilityContextProvider` 已全量实现但未集成到 ContextPolicy 中。当前 DefaultContextPolicy 不接受治理快照参数。

### 4.4 读边界（Read Boundary）

User Space 代码通过 `ReadPorts`（`read_ports.py`）访问投影数据。`ApprovalEngine` 提供审批查询层，但 `Kernel._consume_pre_approved()` 也直接查询审批（FACT-35 报告的双路径）。

### 4.5 审批双路径

FACT-35: 审批读取存在两条并存路径：
- `ApprovalEngine.list_pending()` → API 层消费
- `Kernel._consume_pre_approved()` → 内部消费（预批准快速通道）
两者调用相同的 `kernel.query_state("approvals", ...)`，但无共享抽象。

---

## 5. 存储模型

### 5.1 主存储：SQLite（WAL 模式）

所有写操作通过 `emit_event()` 在一个事务内完成：写 event_log + 运行 Projectors。投影表与事件日志始终一致（FACT-1, FACT-5）。

### 5.2 表分类

| 分类 | 表 | 写入规则 |
|---|---|---|
| **GOVERNED** (14 张表) | event_log, goals, actions, tasks, memories, approvals, conversations, messages, notifications, projection_checkpoints, handler_executions, timer_events, policy_events, grant_events | 仅 Kernel ABI (emit_event → Projectors) |
| **APP_STORAGE** (11 张表) | events, activity_log, llm_calls, tool_calls, background_tasks, triggers, user_profile, inbox_emails, patterns, schedules, app_settings | 应用代码可直读写 |

GOVERNED 表只能通过 `emit_event()` 写入。CI 强制执行（`check_boundary.py`）。

### 5.3 派生索引：ChromaDB

仅用于语义记忆搜索。两阶段同步（FACT-23, ADR-2025-003）：

1. **预计算阶段** (emit_event 事务内): 调用 `vector_store.delete_memory()` + `vector_store.add_memory()`，将 `embedding_id` 写入 SQLite 投影行。
2. **修复阶段** (事务提交后): `_sync_memory_index()` 重试失败的嵌入，删除已标记的记忆，推送 `memory_changed` SSE 通知。

### 5.4 Telemetry（遥测）

FACT-31: 工具调用通过 `telemetry.record_tool_call()` 记录到 `tool_calls` 表。LLM 调用记录到 `llm_calls` 表。API 端点 `/api/telemetry/tool-calls` 和 `/api/telemetry/tool-summary` 暴露此数据。

---

## 6. 模块职责

### Kernel Space（`core/runtime/kernel/`）— B-001

| 模块 | 职责 |
|---|---|
| `kernel.py` | Kernel 类本体，emit_event + dispatch + submit_command |
| `event.py` | Event 不可变数据类 |
| `projectors*.py` | 7 个投影模块，覆盖所有 GOVERNED 表 |
| `projectors_registry.py` | @projector 装饰器 + apply() + owned_tables |
| `kernel_governance.py` | 审批生命周期（GovernanceMixin） |
| `kernel_query_state.py` | 从投影表读取状态（QueryStateMixin，12 个 _query_* 方法） |
| `kernel_sovereignty.py` | 数据导出/导入/重建（SovereigntyMixin） |
| `work_item_repository.py` | WorkItem 持久化与恢复读取 |
| `_mixin_protocol.py` | Kernel 接口协议（Protocol） |

### Runtime Subsystems（`core/runtime/`）— B-002, B-004, B-005

| 模块 | 职责 |
|---|---|
| `agent_bus.py` | Agent 间事件分发（fnmatch 匹配，双投递：队列 + 直接） |
| `agent_scheduler.py` | WorkItem 生命周期引擎（50ms tick, max 8 并发） |
| `agent_registry.py` | Agent 实例管理 |
| `handler_registry.py` | Event Type → Handler 映射（@subscribe 装饰器，6 个已注册） |
| `capability_decision.py` | 四门授权裁决（CapabilityGateway） |
| `capability_policy.py` | 事件溯源的能力策略 |
| `approval_engine.py` | 审批查询层（只读） |
| `timer_engine.py` | 定时/周期触发引擎（1s 扫描） |
| `cron_registry.py` | 8 个 Cron 计划注册和初始化 |
| `trigger_engine.py` | 条件触发器（停滞、阈值） |
| `background_worker.py` | 后台任务轮询（10s） |
| `state_manager.py` | Task 7 状态 FSM |
| `task_engine.py` | Goal/Project/Task CRUD |
| `execution_context.py` | Handler 的最小执行上下文（dataclass） |
| `principal.py` | 类型化身份 |
| `taint.py` | 污点追踪（ContextVar） |
| `runtime_container.py` | 集中式子系统注册表（12+ lazy properties） |
| `conversation_recorder.py` | 对话记录 |
| `notification_bridge.py` | WebSocket 通知桥接（sync/async 双模式） |
| `legacy_event_adapter.py` | 遗留事件格式适配（DEPRECATED but ACTIVE — 3 callers: read_ports, goals, world_model） |

### Agent Layer（`core/agents/`）

| 模块 | 职责 |
|---|---|
| `brain.py` | 无状态 LLM 推理循环（multi-provider failover） |
| `tool_dispatcher.py` | 工具调用分发（顺序执行，独立工具间无通信） |
| `conversation.py` | 对话 CRUD |
| `memory_engine.py` | 记忆生命周期（事件溯源写入） |
| `memory_extractor.py` | 对话中提取记忆（fire-and-forget） |
| `llm_failover.py` | 多提供商 LLM 故障转移 |
| `token_counter.py` | Token 计数（tiktoken） |
| `user_profile.py` | 用户画像（直写 SQLite，偏离事件溯源） |
| `world_model.py` | 世界模型上下文 |
| `mvp/bypass_handlers.py` | 4 个 bypass 处理器（approve, execute, bg_task, inbox_poll） |
| `mvp/chat_handler.py` | 聊天请求处理 |
| `mvp/timer_trigger_handler.py` | 定时触发处理 |

### Harness（`core/harness/`）— B-003

| 模块 | 职责 |
|---|---|
| `mcp_hub.py` | 中心工具注册 + 调用（37 个 builtin tools, flat dict） |
| `mcp_mesh.py` | 外部 MCP 服务器发现和通信（stdio 子进程） |
| `builtin_tools/` | 14 个内置工具实现模块 |

### Governance Context（`core/runtime/governance/`）— B-008

| 模块 | 职责 |
|---|---|
| `context_pipeline.py` | Context 编译管道 |
| `context_policy.py` | ContextPolicy Protocol + DefaultContextPolicy |
| `fragment_selector.py` | Fragment tier 选择 |
| `query_analyzer.py` | 用户消息分析 |
| `capability_context.py` | 能力上下文（DORMANT: 无生产消费者） |
| `execution_context.py` | 治理执行上下文（DORMANT: 无生产消费者） |

### Fragments（`fragments/`）

13 个 Context Fragment 实现，分为三类：
- **Core**: Memory, Goals, World, Conversation State
- **Preference/Knowledge**: Knowledge, Actions, Events
- **Scenario**: Calendar, Mail

### Product（`product/`）

App 层产品功能：数字遗产导出、加密同步、收件箱、通知、仪表盘。

### Storage Layer（`store/`）

SQLite 数据库封装、Schema DDL、Alembic 迁移、ChromaDB 向量存储。

---

## 7. CI 强制约束

CI（`.github/workflows/ci.yml`）强制执行以下架构约束：

1. **Kernel 边界守卫**: `check_boundary.py` 扫描所有 Python 代码，确保无任何文件直接向 GOVERNED 表写入
2. **执行所有权守卫**: `check_execution_ownership.py` 确保所有 `invoke_capability` 调用携带 `execution_id`
3. **投影溯源守卫**: `check_projection_provenance.py` 验证投影行可追溯到 event_log
4. **事件日志重建**: `verify_rebuild.py` 验证从 event_log 确定性重建所有投影表
5. **导出往返**: `verify_export_roundtrip.py` 验证数据导出/导入完整性
6. **向量一致性**: `verify_vector_consistency.py` 验证 SQLite 和 ChromaDB embedding_id 一致
7. **覆盖率门槛**: 运行时覆盖率 ≥ 84%，API 覆盖率 ≥ 70%

---

## 8. 依赖方向

```
API Layer (FastAPI routers, 17 route groups)
    → ContextPipeline (Governance)
        → FragmentRegistry (Fragments)
    → Brain (Agent Layer)
        → ToolDispatcher
            → CapabilityGateway (Authorization)
                → Kernel ABI
                    → event_log + Projectors + Storage
```

一切向下依赖 Kernel（B-001）。Kernel 不依赖 User Space 的任何代码（除了同属 Kernel Space 的 Projectors）。

---

## 9. 已知架构债务

| 项目 | 严重程度 | Trace | 说明 |
|---|---|---|---|
| UserProfile 直写 SQLite | 中 | FACT-26, ADR-2026-006 | `user_profile` 表绕过 Kernel，不可审计。归类为 APP_STORAGE 但建议事件溯源化。 |
| 审批双路径读取 | 低 | FACT-35 | ApprovalEngine 和 Kernel._consume_pre_approved 复制相同读取逻辑。 |
| Governance snapshots 未消费 | 中 | FACT-36 | ExecutionContextProvider / CapabilityContextProvider 全量实现但无接入点。 |
| 三个独立后台循环 | 中 | FACT-7/12/13 | Scheduler, TimerEngine, BackgroundWorker 三循环计划在 v0.3 统一（ROADMAP M1）。 |
| legacy_event_adapter 仍活跃 | 中 | FACT-C2-01 | 标记 DEPRECATED 但 3 个生产调用者（read_ports, goals, world_model）。删除前必须先迁移。 |
| 死事件类型未删除 | 低 | FACT-38/39 | BeliefFormed, AgentSpawned, AgentTerminated 声明但永不 emit。 |
| _smart_notification_check 过滤失效 | 高 | FACT-37 | 传递不被支持的 filter 参数导致去重逻辑无效。 |
