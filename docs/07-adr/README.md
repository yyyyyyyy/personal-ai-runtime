# Architecture Decision Records

本目录登记本轮架构尽调整改落地的决策。代码与 CI 为权威；ADR 解释动机与边界。

| ID | Title |
|----|-------|
| [ADR-R009](ADR-R009-single-process-control-plane.md) | 单进程控制面（多 worker Non-goal） |
| [ADR-R010](ADR-R010-durable-lane-a-cancel.md) | Lane A 取消先持久化再 task.cancel |
| [ADR-R011](ADR-R011-chat-approval-continuation.md) | Chat 审批后续写为 one-shot，不跨进程重开工具环 |
| [ADR-R012](ADR-R012-god-subsystem-budgets.md) | God façade 与子系统 LOC 分项预算（G2） |
| [ADR-R013](ADR-R013-knowledge-path-b.md) | Knowledge 保持 Path B（核实后决策门） |
| [ADR-R014](ADR-R014-handler-executions-soft-prune.md) | handler_executions 终端态 soft-prune（维护特权） |
