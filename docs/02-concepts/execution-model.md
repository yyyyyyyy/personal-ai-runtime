# Execution Model（三车道）

Personal AI Runtime 的所有执行路径用**一套三车道语义**解释。不要再引入平行的「Agent 调度 / 旁路 RPC / 特殊循环」叙事。

## 定义

| Lane | 名称 | 是什么 | 入口 | 持久化 |
|------|------|--------|------|--------|
| **A** | Scheduled Work | 一次 Handler 调用（`ScheduledExecution`） | `emit_event` → Scheduler fan-out | `handler_executions` + Execution* 事件 |
| **B** | Sync Capability | 受治理的外部效果 | `Kernel.invoke_capability` | Capability* 事件（不经 Scheduler） |
| **C** | Maintenance | 时钟驱动的组合动作 | `RuntimeLoop` / `@reaction` | 仅当其 emit / invoke 时进入 A 或 B |

## 概念对照

| 说法 | 含义 |
|------|------|
| 一次 **ScheduledExecution** | Lane A：一个 handler × 一个触发事件 |
| 一次 **Work（领域）** | `work_items` 投影行（goal / task / action）——与 Lane A 不同名不同表 |
| 一次 **Capability Invocation** | Lane B：门控 + `mcp_hub.invoke_tool` + 审计事件 |
| Runtime 调度 | Lane A Scheduler + Lane C RuntimeLoop |
| 同步调用 | Lane B（及 `submit_command` 对完成事件的 Future 等待） |
| 异步执行 | Lane A（async dispatcher → ScheduledExecution） |

## 不变量

1. **一事件可扇出 N 个 Lane A 执行**：`HandlerRegistry` 对同一 `event.type` 保留 handler 列表；Scheduler 为每个 handler 建一个 `ScheduledExecution`。
2. **Lane B 不是 WORK**：工具循环需要同步返回值；CAPABILITY 与 WORK 是不同原语（见 [runtime-algebra.md](runtime-algebra.md)）。
3. **Lane C 不是新原语**：Reaction / timer maintenance 是 `subscribe + emit/invoke` 的组合。
4. **GOVERNED 状态只经投影写入**：包括审批过期（emit `ApprovalDenied` + projector）。

## 代码锚点

- Lane A：[`scheduled_execution.py`](../../backend/app/core/runtime/scheduled_execution.py)、[`agent_scheduler.py`](../../backend/app/core/runtime/agent_scheduler.py)、[`handler_registry.py`](../../backend/app/core/runtime/handler_registry.py)
- Lane B：[`governance_ops.invoke_capability`](../../backend/app/core/runtime/kernel/governance_ops.py)、[`capability_governance.py`](../../backend/app/core/runtime/capability_governance.py)
- Lane C：[`runtime_loop.py`](../../backend/app/core/runtime/runtime_loop.py)、[`reaction_registry.py`](../../backend/app/core/runtime/reaction_registry.py)
