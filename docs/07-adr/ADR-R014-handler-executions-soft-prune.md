# ADR-R014 — Soft-prune handler_executions (maintenance privilege)

| Field | Content |
|-------|---------|
| Decision | RuntimeLoop 可对终端态（completed/failed）且过期的 `handler_executions` 行做 Kernel-space `DELETE`（soft-GC）；**不**删 `event_log` |
| Context | 投影无限增长；ownership 只需近期/进行中行；完整事件删除/压缩为 Non-goal |
| Evidence | `sovereignty_ops.prune_handler_executions`；`runtime_loop._prune_handler_executions`；INV-S1a |
| Consequences + | 热路径表可控；配置 `handler_executions_retention_days` |
| Consequences − | 与「投影只由 projector 写入」字面冲突 → 登记为维护特权例外；`rebuild_all` 仍会从 event_log 重建被删行 |
| Still valid? | Yes until event compaction exists |
