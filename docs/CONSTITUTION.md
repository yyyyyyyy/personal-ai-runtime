# CONSTITUTION

> 本文档是 Personal AI Runtime 项目的**唯一架构宪法**。
> 它定义项目的身份、边界、原则和架构约束。
> 所有其他文档（ROADMAP、ARCHITECTURE、INVARIANTS）必须从此推导，不得发明新目标。
>
> **版本：v3.0（基于 Truth Audit 2026-06-30）**
> **FACT 追溯源**: `docs/engineering/TRUTH_AUDIT.md`

---

## 1. 产品身份

### 1.1 产品愿景

构建一个**数据主权属于用户、行为可治理、可重建、可审计**的个人 AI 运行时（Personal AI Runtime）。

它不是"又一个 AI 助手应用"。它是一条**治理边界**——把不可信的 AI 代理（Agent）约束在受管通道之内，让一切改变系统或外部世界的行为都留痕、可追溯、可撤销、可治理。

交付形态：一个**本地优先（local-first）、单用户、单进程**的运行时，用户的全部个人数据（事件、状态、记忆）驻留在用户自己的机器上，可一键无损导出，永不被任何厂商锁定。

### 1.2 目标用户

- AI 重度用户（每天与多个 AI 模型交互）
- 隐私敏感用户（不希望个人数据被厂商训练或锁定）
- 希望跨模型保持连续性的人（切换模型不丢失记忆和关系）

### 1.3 核心价值

**跨模型连续性**：用户与 AI 的全部历史——记忆、偏好、关系——属于用户，不随模型切换而丢失。

**数据主权**：导出、迁移、重建、销毁的权力始终属于用户，无条件可执行。

**行为治理**：AI 对用户世界的一切改变——文件、命令、邮件、网络——都经过统一的授权裁决、风险分级、来源追踪，高风险操作必须有人类在环。

### 1.4 产品边界

本项目是**运行时（Runtime）**，不是**应用（App）**。

- Runtime 的职责：治理边界、事件存储、状态投影、能力授权、数据主权。
- App 的职责：仪表盘、设置页、对话界面等产品体验，属于 Runtime 之上的一层。
- App 可以按需要读写存储与展示数据，但不得冒充真相层，也不得替 Agent 绕过治理边界。

### 1.5 长期身份

运行时治理的不是计算资源，而是**用户数字生活中的事实、记忆、能力与行为**。

四个支柱定义了运行时的长期身份：

1. **唯一真相（Single Source of Truth）**：不可变、有序、可重放的事件日志是全部真相的来源。State 可从事件流确定性重建；Memory 可从事件流重新推导。
2. **不可越界（Governed Boundary）**：任何 AI Agent 永远不能直接读写存储、文件系统、网络。它们只能通过受治通道访问世界。
3. **可治理的行为（Governable Action）**：对世界的所有交互经过统一的授权裁决，受风险分级、用户审批、污点追踪约束。
4. **可携带的人生（Portable Life）**：用户与运行时相处的全部历史是用户自己的资产，导出/迁移/删除的权力始终属于用户。

---

## 2. 架构原则

这些原则**定义项目本身**。违反任何一条，就不再是这个项目。不随实现技术栈变化而改变。

### P1 · Event Log 是唯一事实来源

**Trace**: FACT-1 (Kernel 单写边界), FACT-5 (Projectors 注册)

事件日志（Event Log）是系统的黑匣子：只追加、不可变、全局有序、可重放。

- **State**（目标、任务、审批等结构化事实）是物化投影，可由事件流确定性重建（rebuild）。
- **Memory**（从对话与事实推导的信念）必须可重新推导（re-derive）：依据事件流再次得出语义一致的记忆。换用不同模型时，不要求字节级相同，但须保持对事实的忠实。

### P2 · AI Agent 不可直达真相源与外部世界

**Trace**: FACT-1 (Kernel 单写边界), FACT-29 (单入口 invoke_capability)

Agent 不得直接访问事件日志、投影表、文件系统、网络、邮件、Shell。Agent 对世界的改变必须经 Runtime 的受管通道（`invoke_capability`）。

App 不是 Agent。仪表盘等产品界面可按需访问存储，但不得冒充真相层或替 Agent 绕过治理边界。

**已知偏差**: FACT-26 — `UserProfile` 直接写 SQLite，绕过 Kernel。当前仍为 APP_STORAGE 表，需追踪为待解决的架构债务。

### P3 · Agent 副作用必须可审计、可追溯

**Trace**: FACT-18 (ExecutionContext via ContextVar), FACT-31 (ToolCallRecord 遥测)

任何 Agent 产生的副作用必须在治理边界内完成，并在事件流中留下可追溯的因果链（`caused_by` + `correlation_id` + `execution_id`）。不存在隐式、无审计的副作用通道。

### P4 · Capability 必须授权，且 Fail-Closed

**Trace**: FACT-11 (4-gate 授权), FACT-32 (CapabilityGateway 唯一裁决点)

能力调用必须经过统一的授权裁决。授权基于**类型化的身份**（Principal），而非裸字符串或隐式信任。当无法判定授权时，默认**拒绝**（fail-closed）。授权关系本身可重建、可审计、可撤销。

### P5 · Agent 可替换，接入语义应稳定

**Trace**: FACT-9 (单 AgentInstance 引导), FACT-17 (HandlerRegistry @subscribe)

换底层模型、换 Agent 实现、换外部 Agent 框架，不应迫使用户放弃数据主权或治理承诺。具体接口可演进，"Agent 可被替换而不破坏用户数据与治理语义"这一承诺不可放弃。

### P6 · 治理优先于功能（Governance over Features）

**Trace**: FACT-33 (无 feature flag 系统), FACT-34 (分散审计日志)

Runtime 存在的目的是**治理 Agent 的行为**，不是堆叠功能。功能是 Apps，治理是 Runtime。当功能与治理边界冲突时，治理胜出。

### P7 · 数据主权不可侵犯

**Trace**: FACT-4 (SovereigntyMixin), FACT-14 (submit_command)

用户对自己的人生数据拥有完全主权：导出、迁移、重建、销毁的权力始终可执行，且必须由 Runtime 无条件支持。

### P8 · 事件溯源约束真相层，而非全系统

**Trace**: FACT-22 (Memory 事件溯源), FACT-26 (UserProfile 直写 SQLite)

事件溯源是**真相层的约束**，不是"全库每一张表都必须事件溯源"。治理域内的 State、Memory、授权关系以 Event Log 为权威来源；应用层缓存、配置、任务队列等辅助状态允许直接读写，只要它们不冒充真相。

---

## 3. 架构不变量（Invariants）

Each invariant maps to a FACT from `docs/engineering/TRUTH_AUDIT.md` and must be verifiable by CI scripts.

### I-001: Kernel 是唯一写入口
**Statement**: 所有 GOVERNED 表的 INSERT/UPDATE/DELETE 必须仅通过 `kernel.emit_event() → projectors` 路径。
**Trace**: FACT-1, FACT-5
**Verification**: `scripts/check_boundary.py` 扫描全部 Python 文件（CI 强制执行）
**Known Violations**: 无（`user_profile` 表类别为 APP_STORAGE）

### I-002: 投影表与事件日志始终一致
**Statement**: 每行投影必须有对应的 event_log 条目；所有投影可从事件流确定性重建。
**Trace**: FACT-5 (同步事务投影), FACT-7 (Shadow Compare 机制)
**Verification**: `scripts/check_projection_provenance.py` + `scripts/verify_rebuild.py`

### I-003: 能力调用必须经过 4-Gate 裁决
**Statement**: 任何工具执行必须先过 CapabilityGateway.decide(gates 1-4)，且 fail-closed。
**Trace**: FACT-11 (四门授权), FACT-32 (Gate 单一裁决点)
**Verification**: `scripts/check_execution_ownership.py` 确保所有 invoke_capability 携带 execution_id

### I-004: 代理不可写入 GOVERNED 表
**Statement**: 代码文件不得包含对 GOVERNED 表直接 SQL 写入语句（INSERT/UPDATE/DELETE）。
**Trace**: FACT-1, FACT-2
**Verification**: `scripts/check_boundary.py`

### I-005: 数据主权操作可执行
**Statement**: `export_data()`, `import_data()`, `destroy_data()` 必须无条件完成且不留余数据。
**Trace**: FACT-4 (SovereigntyMixin), FACT-14
**Verification**: `scripts/verify_export_roundtrip.py`

### I-006: ChromaDB 与 SQLite 索引一致
**Statement**: ChromaDB 中的 embedding_id 集合必须与 SQLite 的 memories 表中的 embedding_id 集合一致。
**Trace**: FACT-23 (两阶段索引同步)
**Verification**: `scripts/verify_vector_consistency.py`

### I-007: 调度器恢复完整
**Statement**: 重启后，pending/running 状态的 WorkItem 必须恢复到可执行状态。
**Trace**: FACT-7 (Scheduler._recover())
**Verification**: 集成测试 `test_execution_recovery.py`

---

## 4. 子系统边界

### B-001: Kernel 边界
**Owner**: `core/runtime/kernel/`
**Interface**: `emit_event()`, `query_state()`, `read_events()`, `invoke_capability()`, `request_approval()`
**Consumers**: 所有 User Space 代码
**Trace**: FACT-1, FACT-4, FACT-14
**Constraint**: Kernel 禁止依赖 User Space 模块；依赖方向单向（User → Kernel）。

### B-002: Capability 治理边界
**Owner**: `core/runtime/capability_decision.py` (CapabilityGateway)
**Interface**: `decide(principal, tool_name, args, ...)` → (allowed | denied | deferred)
**Consumers**: `kernel.invoke_capability()` (唯一调用者)
**Trace**: FACT-11, FACT-32
**Constraint**: 所有 Agent 工具调用必须经过此边界；不可绕行。

### B-003: 工具注册边界
**Owner**: `core/harness/mcp_hub.py` (MCPHub)
**Interface**: `register_tool()`, `invoke_tool()`, `get_tool_defs_for_llm()`
**Subsystems**: 37 builtin tools (13 类别), MCP Mesh (外部工具)
**Trace**: FACT-27, FACT-28, FACT-48
**Constraint**: 工具发现只通过 `mcp_hub._tools` 字典；无其他注册路径。

### B-004: 事件分发边界
**Owner**: `core/runtime/agent_bus.py` (AgentBus)
**Interface**: `subscribe(rule, handler)`, `publish(event)`, `deliver_to(agent_id)`
**Consumers**: AgentInstances, Kernel._dispatch()
**Trace**: FACT-8
**Constraint**: AgentBus 是 Event Log 之上的订阅管理层，非独立基础设施。

### B-005: 调度器边界
**Owner**: `core/runtime/agent_scheduler.py` (Scheduler)
**Interface**: `enqueue(instance_id, actor, event)` → WorkItem 状态机
**Subsystems**: TimerEngine (1s), BackgroundWorker (10s) — 三个独立后台循环
**Trace**: FACT-7, FACT-12, FACT-13
**Constraint**: 所有异步工作单元通过此边界入队；最大并发 8。

### B-006: 存储边界
**Owner**: `store/database.py` (Database) + `store/vector.py` (VectorStore)
**Interface**: SQLite (WAL 模式) + ChromaDB (PersistentClient)
**Trace**: FACT-21, FACT-23
**Constraint**: GOVERNED 表 (14) 仅 Kernel 写入；APP_STORAGE 表 (11) 允许应用层直写。

### B-007: API 边界
**Owner**: `app/main.py` (FastAPI app + AuthMiddleware)
**Interface**: 17 API 路由组，WebSocket (通知)，SSE (chat 流式)
**Trace**: FACT-2, FACT-6, FACT-19
**Constraint**: AuthMiddleware 拦截所有 HTTP 请求；白名单路径 5 个。

### B-008: 治理语境边界
**Owner**: `core/runtime/governance/`
**Interface**: ContextPipeline.build(user_message) → system_prompt
**Trace**: FACT-10, FACT-36
**Constraint**: 治理上下文快照（ExecutionContextProvider, CapabilityContextProvider）已实现但未消费——为休眠组件。当启用时，必须通过 ContextPolicy 协议集成。

---

## 5. 架构决策记录（ADR）

### ADR-2025-001: Event Sourcing for Truth Layer
**Status**: Accepted
**Context**: Truth Audit FACT-1 确认 Kernel 是唯一写入口，所有 GOVERNED 表通过事件投影更新。FACT-5 确认 projector 注册机制成熟。
**Decision**: 维持事件溯源作为真相层的唯一写入范式。不扩展事件溯源到所有 APP_STORAGE 表 (FACT-26, P8)。
**Consequences**: GOVERNED 表可重建；性能受限于单事务写；APP_STORAGE 表可直写但不可冒充真相。

### ADR-2025-002: 4-Gate Capability Authorization
**Status**: Accepted
**Context**: FACT-11 确认四门授权模型生效。FACT-32 确认 CapabilityGateway 是唯一裁决点。FACT-30 确认污点追踪提升 write-class 工具的风险等级。
**Decision**: 维持四门模型的顺序不可改变（Policy → Grant → Pre-Approved → Risk）。
**Consequences**: Agent 无绕行路径；用户审批是 Gate 4 的唯一解锁方式。

### ADR-2025-003: ChromaDB as Derived Index
**Status**: Accepted
**Context**: FACT-21 确认 ChromaDB 是 SQLite 的派生索引。FACT-23 确认两阶段同步模式（预计算 embedding_id + 后提交修复）。
**Decision**: ChromaDB 不独立于事件溯源；其内容仅从事件流推导。索引同步失败不阻塞事件提交（进入修复队列）。
**Consequences**: ChromaDB 可随时从事件流重建；嵌入同步延迟不影响主写路径。

### ADR-2026-004: Three Independent Background Loops
**Status**: Accepted (with deprecation intent)
**Context**: FACT-7, FACT-12, FACT-13 确认三个独立后台循环共存：Scheduler (50ms tick), TimerEngine (1s scan), BackgroundWorker (10s poll)。ROADMAP Milestone 1 已计划统一为 RuntimeLoop。
**Decision**: 短期维持现状，不合并。v0.3.0 统一为单一 RuntimeLoop。
**Consequences**: 当前三个循环的交互时序不可预测；CPU 资源碎片化；但三个循环职责明确，未产生生产问题。

### ADR-2026-005: Governance Snapshots Dormant
**Status**: Accepted
**Context**: FACT-36 确认 ExecutionContextProvider 和 CapabilityContextProvider 全量实现但无生产消费者。DefaultContextPolicy 不接受治理快照参数。
**Decision**: 标记为休眠组件，不立即删除或激活。待 ContextPolicy 协议有次要实现者需要这些快照时再激活。
**Consequences**: Context 管线当前基于用户消息推断，未利用运行时治理状态。激活快照可提升 LLM 的上下文质量，但需先在 ContextPolicy 协议上达成共识。

### ADR-2026-006: UserProfile Bypass
**Status**: Proposed
**Context**: FACT-26 确认 `UserProfile` 直接写 SQLite `user_profile` 表，绕过 Kernel 和事件流。`user_profile` 表归类为 APP_STORAGE，因此不违反 I-004。但此路径无法审计、不可重建、不符合 P3（副作用必须可追溯）。
**Decision**: 待定。选项：(a) 将 UserProfile 事件溯源化，(b) 接受其为 APP_STORAGE 并承担无审计风险，(c) 限制 UserProfile 只读。
**Consequences**: 当前状态：用户画像数据不在审计链中。若画像影响 Agent 行为，后果可能是无法追溯的偏差。

---

## 6. 明确不做的事（Non-Goals）

### NG1 · 不做分布式/微服务
单用户、单进程、本地优先。治理边界是逻辑边界，不是网络边界。

### NG2 · 不做通用 PaaS / Agent 编排平台
不为"任意第三方 Agent 应用"提供托管平台。

### NG3 · 不追求接入所有 Agent 框架
接入契约的治理语义稳定即可。新 Agent 通过身份与能力声明接入，不改造治理核心。

### NG4 · 不做多用户隔离
单用户是设计前提。多租户、跨用户权限不在愿景内。

### NG5 · 不做网络级沙箱 / 完整 PII 脱敏
安全模型建立在**本地单用户**前提上。SSRF 防御、Shell 白名单、文件系统边界是工具层缓解。

### NG6 · 不追求全系统事件溯源
见 P8。真相层事件溯源，而非每一张辅助表都进事件流。

### NG7 · 不为短期可用性牺牲边界
当快速交付需要破坏 P1-P8 时，选择不做该功能，或将其降级为可见、可审计、可消除的偏差。

### NG8 · 不追求 AI 自主性（Autonomy）
Runtime 的目标是**治理 Agent**，不是最大化 Agent 自主性。

```
Governance > Autonomy
```

---

## 7. 文档原则

每个文档有且仅有一个职责。不重复、不交叉。

| 文档 | 职责 |
|---|---|
| `CONSTITUTION.md` | 定义项目身份、原则、边界。唯一的架构宪法。 |
| `ARCHITECTURE_GOVERNANCE.md` | 定义项目如何演进：生命周期、PR 类型、文档所有权、审查门、KPI 仪表盘。 |
| `ARCHITECTURE_BUDGET.md` | 定义运行时概念预算：每个概念的分类、当前计数、目标计数。 |
| `ARCHITECTURE.md` | 解释运行时架构：概念、模块、执行流、数据流、存储模型、治理模型。 |
| `INVARIANTS.md` | 定义 CI 强制验证的不可违反规则。每一条必须有机器验证。 |
| `CURRENT_STATE.md` | 描述当前可测量的状态：架构 KPI、代码规模、覆盖率、CI 状态。 |
| `ROADMAP.md` | 定义架构演进路线：每个里程碑的架构目标、预期删除、预期改进。 |
| `product/MANIFESTO.md` | 对外品牌声明。不包含技术细节。 |
| `reference/API.md` | API 参考。 |
| `reference/CONFIGURATION.md` | 配置项参考。 |
| `engineering/TRUTH_AUDIT.md` | 最后一次系统真相审计报告。 |
| `engineering/RUNTIME_STATE.json` | 架构进化流水线状态。 |

### 文档使用规则

- **写新功能时**: 先问"这与哪条 Core Principle 相关？是否违反任何 Non-Goal？"
- **写 ROADMAP 时**: 每个里程碑必须回溯到本文件的 Mission 或某条 Principle。
- **评审架构时**: Core Principles 是合并/拒绝的硬标准，不接受"特殊情况通融"。
- **发生争议时**: 本文档优先于任何 ADR、SPEC、README 或个人偏好。
- **可验证的约束**: 见 INVARIANTS.md——CONSTITUTION 说目标，INVARIANTS 说工程约束。

本文档刻意不提及具体技术栈细节。这些是实现选择，记录在 ARCHITECTURE.md 和 CURRENT_STATE.md，不属于宪法。
