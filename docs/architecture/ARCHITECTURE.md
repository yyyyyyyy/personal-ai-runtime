# ARCHITECTURE

> 本架构支撑三大产品承诺：**记住你**（Event Log + Rebuild）、**尊重你**（Capability Gateway + Approval）、**释放你**（跨模型 + 数据导出）。
>
> 如果你只想了解产品，请阅读 [product/](../product/)。

> **Personal AI Runtime 生产架构的唯一入口。**
>
> 描述**当前真实运行的生产路径**，不包含愿景、历史或已废弃设计。
>
> 当前状态细节（能力清单、成熟度评级、维护协议）见 [CURRENT_STATE](../engineering/CURRENT_STATE.md)。
> 目标愿景见 [NORTH_STAR](../engineering/NORTH_STAR.md)，不可破坏规则见 [INVARIANTS](../engineering/INVARIANTS.md)。

---

## 1. 系统本质

Personal AI Runtime 是一个 **本地单用户 AI 运行时**：

- **Event Sourcing** 保证真相不可改写
- **Kernel** 是唯一治理写入口
- **CapabilityGateway** 控制 Agent 对工具和外部世界的访问
- **ExecutionContext** 将每个副作用绑定到可追溯的执行链

Agent 是临时计算单元，不持有状态，不直接访问存储。

---

## 2. 逻辑分层

```text
┌─────────────────────────────────────────────────────────────┐
│  API 层 (app/api/*)          产品层 (app/product/*)          │
│  Chat / Goals / Tasks / Inbox / Dashboard / Reviews …       │
└───────────────────────────┬─────────────────────────────────┘
                            │ 多数写路径 → kernel.emit_event / invoke_capability
                            │ 少数直写 APP_STORAGE 表
┌───────────────────────────▼─────────────────────────────────┐
│  Runtime Kernel (app/core/runtime/kernel/)                   │
│  · event_log（append-only，DB trigger 强制）                  │
│  · emit_event → projectors 同事务投影                         │
│  · CapabilityGateway / invoke_capability                     │
│  · SovereigntyMixin：export / import / rebuild               │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  调度与执行                                                   │
│  · AgentBus → AgentInstance.dispatch → Scheduler.enqueue     │
│  · WorkItem → _execute_handler → Handler(ctx, event)         │
│  · ExecutionContext + Principal                              │
│  · handler_executions 投影（Execution 聚合）                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Context 编译层                                               │
│  · Chat Layer: PromptCompiler + PromptArtifact               │
│  · Governance: ContextPolicy → CompilePlan → ContextPipeline │
│  · Context Runtime: FragmentRegistry + ContextAssembler      │
│  · Fragments: 只读 Context Adapter，经 Read Ports 进 Kernel  │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Harness (app/core/harness/)                                  │
│  · mcp_hub：内置工具 + 外部 MCP mesh                         │
│  · 工具调用仅经 kernel.invoke_capability 到达                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Storage                                                      │
│  · GOVERNED_TABLES（16 张）— Kernel 投影 + event_log          │
│  · APP_STORAGE_TABLES（9 张）— 允许应用直写                    │
│  · Chroma：memories / knowledge collections                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 生产 Runtime Flow

### 对话路径

```text
HTTP POST /api/chat/{id}/messages (User Message)
    │
    ▼
kernel.emit_event("ChatRequested") ──→ event_log (append-only)
    │
    ▼
Scheduler (agent_scheduler.py)
    │  WorkItem → ExecutionContext (binds execution_id)
    ▼
ChatHandler (chat_handler.py)
    │
    ├── PromptCompiler.compile()
    │   ├── PromptArtifact (static instructions)
    │   └── ContextPipeline.build()
    │       ├── CompileRequest → DefaultContextPolicy.evaluate()
    │       │   ├── QueryAnalyzer.analyze() (rule-based intent tags)
    │       │   └── FragmentSelector.select_for_stage()
    │       │       ├── Core Tier (always loaded)
    │       │       ├── Priority Tier (priority >= threshold)
    │       │       └── Scenario Tier (intent → fragment mapping)
    │       └── CompilePlan → ContextAssembler.assemble()
    │           → Context String
    │
    └── Brain.chat_stream()
        ├── _create_llm_stream() ──→ LLM API (DeepSeek / OpenAI-compatible)
        │   └── prepare_llm_egress() (audit)
        │
        └── [Tool Loop]
            └── kernel.invoke_capability()
                ├── execution_id validation
                ├── CapabilityGateway.decide()
                │   ├── Gate 1: forbidden_by_policy
                │   ├── Gate 2: principal_not_authorized (fail-closed)
                │   ├── Gate 3: pre-approved fast path
                │   └── Gate 4: risk assessment + taint + approval
                └── mcp_hub.invoke_tool()
                    └── CapabilityInvoked event → event_log

ctx.emit("ChatTextDelta") ──→ event_log (streaming chunks)
ctx.emit("ChatCompleted") ──→ event_log
ctx.emit("ChatDone") ──→ event_log

SSE Stream → Frontend
```

### 定时任务路径

```text
TimerEngine → TimerFired event
    │
    ▼
Scheduler → timer_trigger_handler
    ├── belief_reflection → belief_engine.reflect()
    ├── inbox_poll → kernel.submit_command("InboxPollRequested")
    └── ...
```

---

## 4. Governance Boundary

```
┌────────────────────────────────────────────────────────┐
│  User Space (API / Apps / Agent)                       │
│  · emit_event / invoke_capability ONLY                 │
│  · query_state / read_ports (read-only)                │
│  · NEVER: direct DML on GOVERNED tables                │
└──────────────────────┬─────────────────────────────────┘
                       │
               Kernel ABI (唯一入口)
                       │
┌──────────────────────▼─────────────────────────────────┐
│  Kernel Space                                           │
│  · event_log (append-only, DB trigger enforced)         │
│  · emit_event → projectors (same-transaction)           │
│  · CapabilityGateway.decide() (4-gate authorization)    │
│  · Approval + Taint enforcement                         │
│  · Sovereignty: export / import / rebuild               │
└─────────────────────────────────────────────────────────┘
```

### 表分类契约

| 类别 | 数量 | 访问规则 | 示例 |
|------|------|---------|------|
| **GOVERNED** | 16 表 | 仅 Kernel 写入，经 Event Log 投影 | goals, memories, approvals, messages |
| **APP_STORAGE** | 9 表 | 允许应用直写 | inbox_emails, llm_calls, triggers, user_profile |

权威集合（数量会随版本演进）：`backend/app/store/table_registry.py`。CI 强制每张业务表归类。

CI 强制：`check_boundary.py` 扫描全量代码，禁止 User Space 对 GOVERNED 表 DML。

---

## 5. Runtime Primitives

| 原语 | 定义 | 实现位置 |
|------|------|---------|
| **Event** | 不可变、有序、可重放的事实记录 | `kernel/event.py` |
| **Event Log** | append-only 事实流，系统唯一真相 | `kernel/kernel.py` event_log 表 |
| **Projection** | Event Log 的物化视图（可重建） | `kernel/projectors_core.py` 等 |
| **ExecutionContext** | handler 执行的运行时上下文，绑定 execution_id | `execution_context.py` |
| **Capability** | Agent 可调用的工具，受授权和审批约束 | `capability_decision.py` |
| **Context Fragment** | 为 LLM 提供认知上下文的只读适配器 | `fragments/universal/*.py` |
| **Context Policy** | Fragment 选择与排序策略 | `governance/context_policy.py` |
| **Approval** | 高风险能力需要用户确认，绑定参数且不可重放 | `approval_engine.py` |

---

## 6. Context 编译层详情

Chat 层与 Runtime Governance 层的依赖方向：

```text
Chat (PromptCompiler)
  └─ depends on → Runtime Governance (ContextPipeline)
                    └─ depends on → ContextPolicy (DefaultContextPolicy)
                          └─ uses internally → QueryAnalyzer, FragmentSelector
                    └─ depends on → Context Runtime (FragmentRegistry)
                    └─ depends on → ContextAssembler
                    └─ depends on → Fragments (register_all_fragments)

Governance MUST NOT depend on Chat.
```

### Stage 矩阵（DefaultContextPolicy）

| Stage | Fragment 选择 | Budget | 用途 |
|-------|--------------|--------|------|
| **chat** | Core + Priority + Scenario | 请求值（默认 32000） | 默认对话上下文 |
| **post_tool** | `core.memory`, `core.conversation_state` + Scenario | min(请求, 24000) | 工具执行后续航 |
| **brief** | `core.goals`, `core.reviews`, `core.world`, `calendar.*` | min(请求, 16000) | 简报/摘要 |

### Policy 覆盖

| 入口 | Stage | 经 Policy |
|------|-------|-----------|
| `ChatRequested` → `chat_handler` | `chat` | PromptCompiler → ContextPipeline → Policy |
| Approval resume → `brain_completion` | `post_tool` | PromptCompiler → ContextPipeline → Policy |
| Morning brief (API / Timer) | `brief` | ContextPipeline.build_from_request → Policy |

### Fragment Read Boundary

Fragment 是 Context Adapter，不是 Repository。所有数据读取经 **Read Ports** 进入 Kernel：

```text
Fragment → app/core/runtime/read_ports.py → Kernel.query_state / recall_* → Projection
```

CI 有 `test_fragment_read_boundary.py` 做 AST 扫描守卫（INV-R1）。

---

## 7. 数据主权

- **Event Log** 不可变（DB trigger 拒绝 UPDATE/DELETE）
- **Governed projections** 清空后可由 Event Log 确定性 `rebuild`（CI 验证字节级一致）
- **Export / Import** 往返经 `verify_export_roundtrip.py` 验证
- **Storage**: SQLite + ChromaDB，数据驻留本机

---

## 8. 已确认不在生产路径的组件

| 组件 | 文件 | 状态 |
|------|------|------|
| GovernancePolicyEngine | `governance/governance_policy_engine.py` | 仅测试使用，生产走 DefaultContextPolicy |
| GovernancePolicy | `governance/context_policy.py:162` | 包装器，零生产实例化 |
| ExecutionPlan | `execution/execution_plan.py` | 零生产创建 |
| ExecutionRuntime | `execution/execution_runtime.py` | 零生产实例化 |
| ExecutionConstraints | `execution/execution_constraints.py` | 仅作为 ExecutionPlan 字段 |
| execution/capability_gateway.py | `execution/capability_gateway.py` | 构造函数依赖不存在的 ExecutionPlan |
| AGENT_MANAGER_V2 | `config.py:109` | 定义但从未被任何代码读取 |

---

## 9. CI 守护的不变量

`.github/workflows/ci.yml` 运行以下守卫脚本：

| Step | 守护内容 |
|------|----------|
| `pytest tests/` + coverage ≥80% | Runtime 模块单元/集成测试 |
| `verify_rebuild.py` | 12 张投影表事件重建 |
| `verify_export_roundtrip.py` | 数据主权往返 |
| `verify_snapshot_rebuild.py` | 增量 checkpoint 重建 |
| `check_boundary.py` | User Space 不得 DML 治理表 |
| `check_execution_ownership.py` | `invoke_capability` 须传 `execution_id` |
| `check_projection_provenance.py` | goals/approvals/handler_executions join event_log |
| `verify_egress.py` | 出站审计事件 |
| `verify_connector.py` | calendar connector 进 event_log |
| `verify_pattern_rebuild.py` | Pattern 投影 rebuild |
| `verify_belief_pipeline.py` | Pattern → BeliefFormed → memories rebuild |
| `verify_vector_consistency.py` | SQLite ↔ Chroma ID 一致性 |
| `verify_belief_quality.py` | Belief 质量（traceability/novelty/actionability） |
| `verify_belief_survival.py` | Belief 存活率统计 |
| `verify_pattern_idempotency.py` | Pattern 检测幂等性 |

全部 20+ 条不变量均为 **Tier 1（CI/测试阻断）**，详见 [INVARIANTS.md](INVARIANTS.md)。

---

## 文档导航

| 文档 | 角色 |
|------|------|
| [NORTH_STAR](../engineering/NORTH_STAR.md) | 目标宪法（v1.0 冻结） |
| [INVARIANTS](../engineering/INVARIANTS.md) | 可验证规则（Tier 1/2） |
| **[CURRENT_STATE](../engineering/CURRENT_STATE.md)** | **架构账本** — 能力清单、成熟度、维护协议 |
| [GOVERNANCE](GOVERNANCE.md) | Context 治理与 Policy 细节 |
| [ROADMAP](../product/ROADMAP.md) | 未来方向与下一阶段 |
