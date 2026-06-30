# ARCHITECTURE BUDGET

> 本文档定义运行时概念预算。
> 每个概念有分类、边界 ID、当前计数、目标计数。
> 新增概念 = 必须同时删除或降级一个概念。
>
> **版本：v3.0（基于 Truth Audit 2026-06-30）**
> **FACT 追溯源**: `docs/engineering/TRUTH_AUDIT.md`
> **Constitution 边界**: `docs/CONSTITUTION.md` §4

---

## Budget Units

- **Unit**: 概念/模块/组件计数
- **Last Updated**: 2026-06-30
- **Measurement**: Counted from Truth Audit scan of ~234 Python source files

---

## 1. 运行时概念预算

| Boundary | 类别 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|---|
| B-001..B-008 | Core（核心概念） | 15 | ≤ 10 | FACT-1..20 | Event/Kernel/Capability/Scheduler 是真正核心。其余应降为 Supporting。 |
| — | Supporting（支撑概念） | 32 | ≤ 20 | FACT-21..48 | 支撑概念是实现细节。当前暴露过多。合并审批、统一调度可大幅缩减。 |
| — | Dormant（休眠） | 2 | 激活或删除 | FACT-36 | ExecutionContextProvider, CapabilityContextProvider 全量实现但无消费者。 |
| — | Deprecated（废弃） | 3 | 0 | FACT-38/39/43 | BeliefFormed, AgentSpawned/Terminated, legacy_event_adapter。 |
| — | Dead（死） | 1 | 0 | FACT-44 | RecallRanker 未使用。 |

---

## 2. 调度器预算

| Boundary | 项目 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|---|
| B-005 | 调度引擎 | 3 (Scheduler, TimerEngine, BackgroundWorker) | 1 | FACT-7/12/13 | 三调度方式造成概念碎片。三者都是"在条件下执行某事"的变体。 |
| — | Cron 注册 | 1 (CronRegistry, 8 schedules) | 1 | FACT-12 | 保持。 |
| — | 触发引擎 | 1 (TriggerEngine) | 0 → 合并 | — | 条件触发器是特殊调度。30min cron 是通用调度模式的特例。 |

---

## 3. 审批系统预算

| Boundary | 系统 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|---|
| B-002 | 审批相关概念 | 3 (ApprovalEngine, CapabilityGateway, CapabilityPolicy) | 1 | FACT-32/35 | CapabilityGateway 裁决 + CapabilityPolicy 策略 + ApprovalEngine 查询 = 同一系统不同面。 |
| B-001 | 审批入口 | 1 (GovernanceMixin on Kernel) | 1 | FACT-14 | 保持。 |

---

## 4. 规划系统预算

| 系统 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|
| 规划系统 | 0 | 0 | — | Planner/Critic 已在 v0.2.0 删除。Runtime 治理行为，不规划行为。 |
| Task/Goal 引擎 | 2 (TaskEngine, StateManager) | 1 | FACT-20 | TaskEngine 发事件，StateManager 验证 FSM——应合并。 |

---

## 5. 事件总线预算

| Boundary | 系统 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|---|
| B-004 | 事件分发 | 1 (AgentBus) | 1 | FACT-8 | 保持。一个事件总线的语义清晰。 |
| — | 通知分发 | 1 (NotificationBridge) | 合并到 AgentBus | FACT-15 | WebSocket 通知是 AgentBus 的消费者，非独立事件系统。 |

---

## 6. 后台循环预算

| 循环 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|
| 后台循环 | 3 (TimerEngine 1s, BackgroundWorker 10s, Scheduler 50ms) | 1 | FACT-7/12/13 | 三个循环 = 三种 tick 频率 + 三种扫描逻辑。应统一为事件驱动主循环。 |

---

## 7. 全局单例预算

| 单例 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|
| 模块级单例 | 5+ (kernel, agent_bus, taint_registry, capability_policy, mcp_hub 等) | ≤ 2 (Kernel + RuntimeContainer) | FACT-3 | 分散的模块级单例阻碍测试隔离。RuntimeContainer 已开始集中管理。 |
| RuntimeContainer | 1 | 1 | FACT-3 | 唯一应存在的子系统注册表。 |

---

## 8. Context Fragment 预算

| 类别 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|
| Context Fragment 实现 | 13 | ≤ 8 | — | 13 个 Fragment 造成 token 预算管理复杂。合并 Actions+Events, Calendar+Mail。 |

---

## 9. 工具类别预算

| Boundary | 类别 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|---|
| B-003 | Builtin 工具类别 | **13** | ≤ 8 | FACT-27 | Truth Audit 确认 13 类别（非 12），37 工具（非 28+）。部分类别使用率极低，应移至 External MCP。 |
| B-003 | Builtin 工具总数 | **37** | ≤ 20 | FACT-27 | 每新增一个工具 = 新增一条策略 + 一条污点规则 + 测试。 |
| B-003 | External MCP 工具 | N (动态) | N | FACT-28 | MCP Mesh 动态发现，不占用 builtin 预算。 |

### 类别分布（Truth Audit）

| # | 类别 | 工具数 | 迁移建议 |
|---|------|--------|----------|
| 1 | time | 1 | 保持 |
| 2 | filesystem | 5 | 保持 |
| 3 | web | 2 | 合并 web_search + fetch_url |
| 4 | calendar | 3 | 保持 |
| 5 | email | 3 | 保持 |
| 6 | browser | 2 | 合并到 web 类别 |
| 7 | clipboard_ocr | 2 | → External MCP |
| 8 | shell | 1 | 保持 |
| 9 | git | 3 | 保持 |
| 10 | telegram | 2 | → External MCP |
| 11 | goals | 4 | 保持 |
| 12 | computer_use | 7 | → External MCP |
| 13 | voice | 2 | → External MCP |
| **总计** | **13** | **37** | **→ 8 类别, ≤20 工具** |

---

## 10. API 路由预算

| 类别 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|
| API 路由组 | 17 | ≤ 12 | FACT-2 | timeline, triggers, background_tasks, connectors 暴露内部概念。公共 API 应只暴露产品概念。 |

---

## 11. 数据表预算

| 类别 | 当前计数 | 目标 | Trace | 理由 |
|---|---|---|---|---|
| GOVERNED 表 | 14 | ≤ 12 | FACT-1/5 | 每张 GOVERNED 表 = 事件类型 + 投影器 + 重建验证。 |
| APP_STORAGE 表 | 11 | ≤ 6 | FACT-26/38 | events, schedules, patterns 是遗留表。清理后可减至 8。 |
| 遗留表 | 3 (events, schedules, patterns) | 0 | FACT-38/43 | 须在 v0.3/v0.3.1 清理。 |

---

## 12. 新增约束：死代码预算

Truth Audit 发现的具体死代码项：

| 项目 | 当前状态 | Target | Trace |
|---|---|---|---|
| 死事件类型 | 3 (BeliefFormed, AgentSpawned, AgentTerminated) | 0 | FACT-38/39 |
| 废弃函数 | 2 (estimate_tokens, log_activity) | 0 | FACT-41/42 |
| 未使用类 | 1 (RecallRanker) | 0 | FACT-44 |
| 遗留适配器 | 1 (legacy_event_adapter) | 0 | FACT-43 |
| 空查询路径 | 1 (_APPLICATION_EVENT_TYPES) | 0 | FACT-40 |
| 重复 SQL 构建 | 1 (query_state vs query_builder) | 0 | FACT-45 |
| 功能 bug | 1 (_smart_notification_check 过滤失效) | 0 | FACT-37 |

---

## 总结：目标 v1.0 架构

| 维度 | v0.2 当前 | Truth Audit 修正 | v1.0 目标 |
|---|---|---|---|
| 运行时概念总数 | 47 | 47 | ≤ 25 |
| Core 概念 | 15 | 15 | ≤ 10 |
| 调度引擎 | 3 | 3 | 1 |
| 审批系统 | 3 | 3 | 1 |
| 后台循环 | 3 | 3 | 1 |
| 全局单例（非 Container） | 5+ | 5+ | 0 |
| Context Fragment | 13 | 13 | ≤ 8 |
| Builtin 工具类别 | 12 | **13** | ≤ 8 |
| Builtin 工具总数 | 28+ | **37** | ≤ 20 |
| API 路由组 | 17 | 17 | ≤ 12 |
| GOVERNED 表 | 14 | 14 | ≤ 12 |
| APP_STORAGE 表 | 11 | 11 | ≤ 6 |
| 重复系统 | 3 | 3 | 0 |
| 遗留适配器 | 1 | 1 | 0 |
| 死事件类型 | 未知 | **3** | 0 |
| 休眠治理组件 | 未知 | **2** | 0 |
| 未使用类 | 未知 | **1** | 0 |
| 空查询路径 | 未知 | **1** | 0 |

v1.0 的定义：架构预算达标，无遗留系统，无重复系统，无休眠组件，无死代码。
