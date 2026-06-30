# ROADMAP — Architecture Evolution

> 本文档定义架构演进路线。它不定义功能路线图（功能属于 App 层），只定义架构目标。
> 每个里程碑描述架构改进、预期简化、预期删除。
> 所有里程碑必须回溯到 CONSTITUTION.md 的核心原则或 ARCHITECTURE_BUDGET.md 的预算目标。
>
> **版本：v3.0（基于 Truth Audit 2026-06-30）**

---

## 当前版本: v0.2.0

已完成：事件溯源内核、四门能力授权、Kernel 边界守卫、投影重建、数据主权导出/导入、架构整合（删除 24 个死模块，净 -3,154 行）。

2026-06-30 Truth Audit 发现（48 FACTs）：
- 2 个休眠治理组件（ExecutionContextProvider, CapabilityContextProvider — FACT-36）
- 3 条死事件类型（BeliefFormed, AgentSpawned, AgentTerminated — FACT-38/39）
- 1 个功能 bug（_smart_notification_check 过滤失效 — FACT-37）
- 1 个架构偏离（UserProfile 直写 SQLite — FACT-26, ADR-2026-006）
- 1 个活跃的遗留适配器（legacy_event_adapter 仍被导入 — FACT-43）
- 2 条代码重复（审批双路径 FACT-35, query_state SQL 构建重复 FACT-45）
- 37 个 builtin 工具（远超 28+ 估算 — FACT-27）

---

## Milestone 1: Runtime Unification

**目标架构版本：v0.3.0**

### 架构目标

统一运行时调度。当前三种调度引擎（Scheduler 50ms tick、BackgroundWorker 10s poll、TimerEngine 1s scan）各自独立运行，造成概念碎片、资源浪费和难以理解的执行时序。

**Truth Audit Trace**: FACT-7, FACT-12, FACT-13, ADR-2026-004

### 预期简化

- 合并 Scheduler + BackgroundWorker + TimerEngine → 单一 `RuntimeLoop`
- 单一 tick 频率，按优先级调度不同类型的 WorkItem（即时执行 vs 定时执行 vs 后台清理）
- 消除 BackgroundWorker 的独立 poll 循环
- 消除 TimerEngine 的 1s 扫描循环

### 预期删除

- `background_worker.py` → 合并到 RuntimeLoop
- `timer_engine.py` → 合并到 RuntimeLoop
- 独立的 TimerEngine tick → RuntimeLoop 的内部调度
- `legacy_event_adapter.py`（FACT-43: 遗留适配器 target v0.3 删除窗口到期）

### 预期架构改进

- 调度概念：3 → 1（参见 ARCHITECTURE_BUDGET §2）
- 后台循环：3 → 1（参见 ARCHITECTURE_BUDGET §6）
- 执行时序可预测：所有 WorkItem 在一个统一队列中，按优先级和截止时间排序
- 消除遗留适配器：`read_ports.py` 不再依赖 `legacy_event_adapter`

### 预期产品影响

无可见变化。这是纯架构层面的改进，不影响功能。

---

## Milestone 2: Dead Code & Dormant Component Cleanup

**目标架构版本：v0.3.1**

### 架构目标

清理 Truth Audit 发现的死代码和休眠组件。减少代码负担，降低维护成本。

**Truth Audit Trace**: FACT-36/38/39/41/42/43/44, ADR-2026-005

### 预期删除

- `EVENT_BELIEF_FORMED` 和 `AGGREGATE_PATTERN` 常量 + 相关 projector（FACT-38）
- `EVENT_AGENT_SPAWNED` 和 `EVENT_AGENT_TERMINATED` 常量（FACT-39）
- `_APPLICATION_EVENT_TYPES` 空 frozenset 及相关代码（FACT-40）
- `patterns` 表（遗留 DDL）和 `schedules` 表（FACT-38）
- `context_runtime.estimate_tokens()` 废弃函数（FACT-41）
- `activity_log.log_activity()` 单体调用者清理或合并到遥测（FACT-42）
- `RecallRanker` 未使用的评分器（FACT-44）

### 预期架构改进

- 死事件类型：3 → 0
- 废弃函数：2 → 0
- 未使用类：1 → 0
- 净代码行减少：~200 行
- 降低新贡献者困惑

### 预期产品影响

无可见变化。纯清理。

---

## Milestone 3: Bug Fix — Notification Dedup

**目标架构版本：v0.3.2**

### 架构目标

修复 `BackgroundWorker._smart_notification_check` 的过滤失效问题。当前 `_query_notifications` 不支持 `related_id` 和 `notification_type` 参数（FACT-37）。

**Truth Audit Trace**: FACT-37

### 修复内容

- 在 `_query_notifications()` 中添加 `related_id` 和 `notification_type` 过滤支持
- 或改用 `query_builder.py` 的统一 WHERE 构建（FACT-45）

### 预期架构改进

- 停滞目标通知去重逻辑从"几乎无效"变为"正常工作"
- 减少重复通知对用户的干扰

### 预期产品影响

用户收到的重复"停滞目标"通知减少。

---

## Milestone 4: Capability Governance Consolidation

**目标架构版本：v0.4.0**

### 架构目标

合并审批和能力治理相关概念。当前 `CapabilityGateway` 做裁决、`CapabilityPolicy` 存储策略、`ApprovalEngine` 提供查询——三个概念是同一系统的不同面。

**Truth Audit Trace**: FACT-32, FACT-35, ADR-2026-002

### 预期简化

- 合并 CapabilityGateway + CapabilityPolicy + ApprovalEngine → 单一 `CapabilityGovernance`
- 消除审批双路径读取（FACT-35）：Kernel._consume_pre_approved 和 ApprovalEngine 共享同一读取接口
- 策略查询、授权裁决、审批查询通过同一个接口暴露

### 预期删除

- `capability_policy.py` → 合并到 CapabilityGovernance
- `approval_engine.py` → 合并到 CapabilityGovernance

### 预期架构改进

- 审批相关概念：3 → 1（参见 ARCHITECTURE_BUDGET §3）
- 消除双路径读取
- 能力相关的全部逻辑在一个模块中

### 预期产品影响

审批 UI 的 API 调用路径缩短。审批决策延迟降低。

---

## Milestone 5: Global Singleton Elimination

**目标架构版本：v0.5.0**

### 架构目标

消除分散的模块级单例。v0.2.0 引入 `RuntimeContainer` 集中管理子系统，但 kernel、agent_bus、taint_registry 等仍以模块级单例存在。

**Truth Audit Trace**: FACT-3 (RuntimeContainer 惰性属性)

### 预期简化

- 所有子系统通过 `RuntimeContainer` 访问，不再有 `from x import singleton` 模式
- 测试隔离从"手动 reset 每个单例"变为"重建 RuntimeContainer"

### 预期删除

- `kernel_instance.py` → Kernel 仅通过 RuntimeContainer 访问
- 各模块的模块级单例 → 移到 RuntimeContainer 的惰性属性

### 预期架构改进

- 全局单例：5+ → 0（参见 ARCHITECTURE_BUDGET §7）
- 测试隔离从 O(n) 变为 O(1)

### 预期产品影响

测试并行化成为可能，CI 速度提升。

---

## Milestone 6: Context Fragment Streamlining

**目标架构版本：v0.6.0**

### 架构目标

减少 Context Fragment 数量和复杂度。当前 13 个 Fragment 造成 token 预算管理复杂和策略矩阵膨胀。

### 预期简化

- 合并 Actions + Events → 单一 TimelineFragment
- 合并 Calendar + Mail → 单一 IntegrationFragment
- 低频 Fragment 按需加载而非始终注册
- 集成治理快照到 ContextPolicy（激活 FACT-36 的休眠组件）

### 预期删除

- `fragments/universal/actions.py` → 合并
- `fragments/universal/events.py` → 合并
- `fragments/calendar/` → 合并到 IntegrationFragment
- `fragments/mail/` → 合并到 IntegrationFragment

### 预期架构改进

- Context Fragment：13 → ≤ 8（参见 ARCHITECTURE_BUDGET §8）
- Context 管道代码路径更短
- 激活治理快照：LLM 上下文获得运行时状态感知

### 预期产品影响

System prompt 更精炼，LLM 响应质量提升（更少的无关上下文）。Token 消耗降低。

---

## Milestone 7: Tool Budget Compliance

**目标架构版本：v0.7.0**

### 架构目标

将 Builtin 工具类别控制在 8 个以内。当前 37 个 builtin 工具（13 类别）远超大预算目标。低频工具以 External MCP 配置形式提供。

**Truth Audit Trace**: FACT-27 (37 builtin tools), FACT-28 (MCP Mesh), FACT-48 (OpenAI format)

### 预期简化

- clipboard_ocr（2 tools）→ External MCP（使用率极低）
- computer_use（7 tools）→ External MCP（安全风险高，不应内置）
- voice（2 tools）→ External MCP（依赖外部服务）
- 合并 web_search + fetch_url → 单一 WebAccess 类别
- 合并 browser + web → 单一 Web 类别

### 预期删除

- `builtin_tools/clipboard_ocr.py` → 移到外部 MCP 配置
- `builtin_tools/computer_use.py` → 移到外部 MCP 配置
- `builtin_tools/voice.py` → 移到外部 MCP 配置
- `builtin_tools/browser.py` → 合并到 web

### 预期架构改进

- Builtin 工具类别：13 → ≤ 8
- Builtin 工具总数：37 → ≤ 20
- 内核更精干

### 预期产品影响

用户在 Settings 中按需启用外部工具。默认工具列表更简洁。安全面减小。

---

## Milestone 8: UserProfile & Query Builder Consolidation

**目标架构版本：v0.8.0**

### 架构目标

解决 Truth Audit 发现的架构债务。

**Truth Audit Trace**: FACT-26 (UserProfile), FACT-45 (query_builder 重复), FACT-46 (审批重复)

### 修复内容

1. **UserProfile 审计化**: 将 `user_profile` 表改为 Government 或添加审计事件（ADR-2026-006 决议）
2. **统一 WHERE/LIMIT/ORDER 构建**: 将 `kernel_query_state.py` 的手写 SQL 迁移到 `query_builder.py`（FACT-45）
3. **消除审批双路径**: Milestone 4 中已处理

### 预期架构改进

- 统一 SQL 构建路径
- UserProfile 变更可审计
- 消除查询层重复

### 预期产品影响

用户画像变更有审计记录。

---

## Target: v1.0 Architecture

**目标状态（不承诺时间）**

| 维度 | 当前 (v0.2) | Truth Audit 修正 | v1.0 目标 |
|---|---|---|---|
| 运行时概念总数 | 47 | 47 | ≤ 25 |
| Core 概念 | 15 | 15 | ≤ 10 |
| 调度引擎 | 3 | 3 (FACT-7/12/13) | 1 |
| 审批系统 | 3 | 3 (FACT-32/35) | 1 |
| 后台循环 | 3 | 3 | 1 |
| 全局单例（非 Container） | 5+ | 5+ (FACT-3) | 0 |
| Context Fragment | 13 | 13 | ≤ 8 |
| Builtin 工具类别 | 12 | **13** (FACT-27) | ≤ 8 |
| Builtin 工具总数 | 28+ | **37** (FACT-27) | ≤ 20 |
| API 路由组 | 17 | 17 (FACT-2) | ≤ 12 |
| GOVERNED 表 | 14 | 14 | ≤ 12 |
| APP_STORAGE 表 | 11 | 11 (FACT-38: patterns/schedules 遗留) | ≤ 6 |
| 重复系统 | 3 | 3 | 0 |
| 实验概念 | 3 | 3 | 0 |
| 死事件类型 | 未知 | **3** (FACT-38/39) | 0 |
| 休眠治理组件 | 未知 | **2** (FACT-36) | 激活或删除 |
| 遗留适配器 | 1 | 1 (FACT-43) | 0 |

v1.0 的定义：架构预算达标，无遗留系统，无重复系统，无实验功能，无死代码。
