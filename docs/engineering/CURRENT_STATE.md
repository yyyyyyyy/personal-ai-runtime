# CURRENT STATE

> 本文档仅包含**可测量的架构事实**。无意见、无计划、无历史讨论。
> 它是架构的"体检报告"，由 CI 和数据统计自动生成。
> 最后更新: 2026-06-30 (Architecture Evolution Cycle #2, Stage 05)

---

## 1. 架构 KPI

| KPI | 值 | 来源 |
|---|---|---|
| Python 源文件数 | 163 | `find backend/app -name "*.py"` (excl tests) |
| Python 源代码行数 | 21,899 | `wc -l` 聚合 |
| Python 测试文件数 | 121 | `find backend/tests -name "*.py"` |
| Python 测试代码行数 | 12,797 | `wc -l` 聚合 |
| Alembic + Scripts 文件数 | 19 | `find backend/alembic backend/scripts -name "*.py"` |
| Alembic + Scripts 行数 | 2,684 | `wc -l` 聚合 |
| GOVERNED 表 | 14 | `table_registry.py` → GOVERNED_TABLES (含 event_log, projection_checkpoints) |
| APP_STORAGE 表 | 11 | `table_registry.py` → APP_STORAGE_TABLES |
| Builtin 工具注册数 | **37** | `mcp_hub.py` register_tool 计数 (Truth Audit FACT-27) |
| Builtin 工具类别 | **13** | `mcp_hub.py` _register_*_tools 方法计数 |
| API 路由组 | **16** | `main.py` include_router 计数 |
| API 端点总数 | **106** | `api/` 目录下 @router 装饰器计数 |
| Cron 定时任务 | 8 | `cron_registry.py` SCHEDULES 列表 |
| Handler 注册数 | 6 | `@subscribe` 装饰器计数 (Truth Audit FACT-17) |
| Kernel 文件数 | 19 | `kernel/` 目录 |
| Kernel 行数 | 3,233 | `wc -l` 聚合 |
| 模块级单例 | **11** | Verification Report §A10 |
| 死事件类型 | **3** | Truth Audit FACT-38/39 |
| 休眠治理组件 | **2** | Truth Audit FACT-36 |
| 重复系统 | **3** | Truth Audit FACT-35/37/45 |
| 遗留适配器 | **1** (ACTIVE) | Truth Audit FACT-43, Verification 重分类 |

---

## 2. 运行时概念清单

| 序号 | 概念 | 文件 | 分类 | 活跃状态 |
|------|------|------|------|----------|
| 1 | Event | `kernel/event.py` | Core | Active |
| 2 | Kernel | `kernel/kernel.py` | Core | Active |
| 3 | Projector | `kernel/projectors*.py` (7 modules) | Core | Active |
| 4 | CapabilityGateway | `capability_decision.py` | Core | Active |
| 5 | CapabilityPolicy | `capability_policy.py` | Core | Active |
| 6 | AgentBus | `agent_bus.py` | Core | Active |
| 7 | Scheduler | `agent_scheduler.py` | Core | Active |
| 8 | WorkItem | `work_item.py` | Core | Active |
| 9 | HandlerRegistry | `handler_registry.py` | Core | Active |
| 10 | ExecutionContext | `execution_context.py` | Core | Active |
| 11 | Principal | `principal.py` | Core | Active |
| 12 | AgentInstance | `agent_instance.py` | Core | Active |
| 13 | AgentDefinition | `agent_definition.py` | Core | Active |
| 14 | AgentRegistry | `agent_registry.py` | Core | Active |
| 15 | TimerEngine | `timer_engine.py` | Core | Active |
| 16 | CronRegistry | `cron_registry.py` | Core | Active |
| 17 | TaskEngine | `task_engine.py` | Supporting | Active |
| 18 | StateManager | `state_manager.py` | Supporting | Active |
| 19 | BackgroundWorker | `background_worker.py` | Supporting | Active |
| 20 | TriggerEngine | `trigger_engine.py` | Supporting | Active |
| 21 | ApprovalEngine | `approval_engine.py` | Supporting | Active |
| 22 | ContextPipeline | `governance/context_pipeline.py` | Supporting | Active |
| 23 | ContextPolicy | `governance/context_policy.py` | Supporting | Active |
| 24 | FragmentSelector | `governance/fragment_selector.py` | Supporting | Active |
| 25 | QueryAnalyzer | `governance/query_analyzer.py` | Supporting | Active |
| 26 | ReadPorts | `read_ports.py` | Supporting | Active |
| 27 | TaintRegistry | `taint.py` | Supporting | Active |
| 28 | SensitiveRouter | `sensitive_router.py` | Supporting | Active |
| 29 | RuntimeContainer | `runtime_container.py` | Supporting | Active |
| 30 | MCPHub | `harness/mcp_hub.py` | Supporting | Active |
| 31 | MCPMesh | `harness/mcp_mesh.py` | Supporting | Active |
| 32 | Brain | `agents/brain.py` | Supporting | Active |
| 33 | ToolDispatcher | `agents/tool_dispatcher.py` | Supporting | Active |
| 34 | ConversationManager | `agents/conversation.py` | Supporting | Active |
| 35 | MemoryEngine | `agents/memory_engine.py` | Supporting | Active |
| 36 | MemoryExtractor | `agents/memory_extractor.py` | Supporting | Active |
| 37 | LLMFailoverRouter | `agents/llm_failover.py` | Supporting | Active |
| 38 | PromptCompiler | `chat/prompt_compiler.py` | Supporting | Active |
| 39 | ContextAssembler | `assembler/context_assembler.py` | Supporting | Active |
| 40 | FragmentRegistry | `context_runtime.py` | Supporting | Active |
| 41 | ConversationRecorder | `conversation_recorder.py` | Supporting | Active |
| 42 | NotificationBridge | `notification_bridge.py` | Supporting | Active |
| 43 | EgressGate | `egress/egress_gate.py` | Supporting | Active |
| 44 | SSEQueueRegistry | `sse_queue_registry.py` | Supporting | Active |
| 45 | ExecutionContextProvider | `governance/execution_context.py` | Supporting | **Dormant** (FACT-36) |
| 46 | CapabilityContextProvider | `governance/capability_context.py` | Supporting | **Dormant** (FACT-36) |
| 47 | LegacyEventAdapter | `legacy_event_adapter.py` | Supporting | **Active-deprecated** (FACT-C2-01: 3 callers — read_ports, goals, world_model) |
| 48 | WorkflowEditor | (frontend) | Experimental | Downgraded |
| 49 | SceneTemplates | (frontend) | Experimental | Downgraded |
| 50 | IntegrationsHub | (frontend) | Experimental | Downgraded |
| 51 | RecallRanker | `agents/user_profile.py` | Supporting | **Dormant** (FACT-44, 0 imports) |

**概念总数：51**（Core: 16, Supporting: 32, Experimental: 3）

---

## 3. 重复系统

| 重复项 | 说明 | Truth Audit | 状态 |
|---|---|---|---|
| `events` 表 vs `event_log` 表 | 旧事件格式与统一格式 | — | 已知，需清理 |
| `schedules` 表 vs `timer_events` 表 | 旧 cron 方案 vs TimerEngine | — | 已知，保留兼容 |
| `patterns` 表 | Evidence→Pattern→Belief 管道已移除 | — | 遗留 |
| 审批双路径读取 | ApprovalEngine vs Kernel._consume_pre_approved | FACT-35 | **重复 (Verification 确认)** |
| SQL 构建重复 | kernel_query_state.py 手写 WHERE vs query_builder.py | FACT-45 | **重复 (Verification 确认)** |
| 通知去重失效 | _query_notifications 不支持 related_id/notification_type | FACT-37 | **Bug (Verification 确认)** |

---

## 4. 已删除的子系统（v0.2.0）

| 模块 | 删除原因 |
|---|---|
| Planner/Critic | 不属于 Runtime 治理领域 |
| EventBus | 被 AgentBus 替代 |
| PatternAggregator | 已移除 |
| BeliefEngine | 已移除 |
| `scheduler.py` | 重命名为 `cron_registry.py` |
| `llm_router.py` | 重命名为 `llm_failover.py` |

净减少代码：-3,154 行。

---

## 5. 测试覆盖

| 指标 | 值 |
|---|---|
| 测试框架 | pytest (asyncio_mode=auto) |
| 运行时覆盖率门槛 (CI) | >= 84% |
| API 覆盖率门槛 (CI) | >= 50%（当前实际 ~43%，目标 70%） |
| live_llm 标记的测试 | 在 CI 中跳过 |

---

## 6. CI 状态

| CI 步骤 | 状态 |
|---|---|
| Syntax check (compileall) | Pass |
| Ruff lint | Pass |
| Mypy type check | Pass |
| Pytest (runtime coverage >= 84%) | Pass |
| Pytest (API coverage >= 50%) | Pass |
| Alembic schema verify | Pass |
| MCP tools verify | Pass |
| API route loading verify | Pass |
| Event Log rebuild | Pass |
| Export roundtrip | Pass |
| Snapshot rebuild | Pass |
| Kernel boundary guard | Pass |
| Execution ownership guard | Pass |
| Projection provenance | Pass |
| Conversation rebuild | Pass |
| Goal rebuild | Pass |
| Memory lifecycle | Pass |
| Inbox audit | Pass |
| LLM egress audit | Pass |
| Connector verify | Pass |
| Vector consistency | Pass |

---

## 7. 版本

| 属性 | 值 |
|---|---|
| 项目版本 | ⚠️ 漂移：代码 `version.py`=0.1.0, 文档=v0.2.0, `main.py`="local" |
| Python | >= 3.12 |
| Node | >= 20 |
| FastAPI | 0.115.6 |
| SQLite | WAL mode |
| ChromaDB | 0.5.23 |
| 前端框架 | React 19 + Vite 6 + TanStack Query 5 |
| 桌面框架 | Electron 33 |

---

## 8. 架构进化指标

| 指标 | 值 | 来源 |
|---|---|---|
| Truth Audit FACTs | 5 (循环 #2 增量) + 48 (循环 #1) | Stage 01 Cycle #2 (2026-06-30) |
| Constitution Invariants | 7 | Stage 02 (v3.1) |
| Constitution Boundaries | 8 | Stage 02 |
| ADRs | 7 (新增: 007 Legacy Adapter ACTIVE) | Stage 02 Cycle #2 |
| Invariant Compliance | 5/7 (71.4%) — 循环 #2 未重新验证 | Stage 04 Cycle #1 |
| Boundary Compliance | 7/8 (87.5%) | Stage 04 Cycle #1 |
| Implementation PRs | 12 (PR-06 已修订: +goals.py +world_model.py 迁移) | Stage 03 Cycle #2 |
| 计划代码变更 | +1025 / -1393 | Stage 03 |
| Overall Verdict | ⚠️ PARTIALLY COMPLIANT | Stage 04 Cycle #1 |
| Runtime Coverage | 84% | CI (Cycle #2 达标) |
