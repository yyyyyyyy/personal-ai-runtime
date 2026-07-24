# ADR-R010 — Durable Lane A cancel

| Field | Content |
|-------|---------|
| Decision | `Scheduler.request_cancel` 对 in-flight 项先 emit `ExecutionFailed(cancelled)` 再 `task.cancel()` |
| Context | 仅进程内 flag 时，进程在 cancel 与 Failed 投影之间死亡会导致 `running→pending` 复活 |
| Evidence | `agent_scheduler.request_cancel`, `execution.py` 注释 |
| Consequences + | 取消意图进入 governed 投影，恢复路径跳过 |
| Consequences − | 可能与 CancelledError 路径竞态（以 status==failed 跳过双写） |
| Still valid? | Yes |
