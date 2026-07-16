# Kernel ABI（冻结面）

Kernel 是 Runtime 的**稳定边界入口**，不是持续增长的业务门面。

权威纪律：**新能力默认不得修改 Kernel。** 若必须修改，PR 需说明为何不能用 read_ports / harness / handlers / projectors 表达。

## 冻结的公开方法

| 方法 | 原语 | 说明 |
|------|------|------|
| `emit_event` | EVENT | 唯一 GOVERNED 写入口（经同事务投影） |
| `read_events` / `read_events_by_seqs` | EVENT | 真相层读取 |
| `subscribe_events` / `set_async_dispatcher` | WORK 接线 | 同步订阅 + Lane A 异步调度 |
| `submit_command` | EVENT 包装 | emit + await 完成事件 |
| `query_state` | STATE | 投影选择器；新代码优先 `read_ports` |
| `invoke_capability` | CAPABILITY | Lane B 同步 egress |
| `request_approval` / `grant_approval` / `deny_approval` / `expire_stale_approvals` | CAPABILITY | 审批生命周期（过期只 emit） |
| `snapshot` / `restore` / `erase` / `rebuild` / `rebuild_all` / export·import event_log | 主权 | 数据主权与重建 |
| `read_scheduled_execution` | WORK（读） | 按 id O(1) 读 Lane A 投影 |

## 已收紧 / 委托

| 能力 | 位置 | 说明 |
|------|------|------|
| 语义召回 | `MemoryIndexPort.search_*` via `recall_memory` / `recall_knowledge` | 禁止旁路全局 `vector_store` |
| 工具 schema 列表 | `mcp_hub.get_tool_defs_for_llm` | Kernel 仅 thin 转发（勿再扩） |
| ScheduledExecution 扫描 | `execution_repository` | Kernel 包装供 Scheduler 恢复 |
| 按 id 读取执行单元 | `Kernel.read_scheduled_execution(id)` | O(1) 投影查找；Scheduler shadow-compare 必须用此，禁止全表扫 |

## 禁止事项

- 在 Kernel 包内、非 `projectors_*.py` / 主权重建路径，对 GOVERNED 表做 DML（由 `check_boundary.py` 扫描）。
- 为产品功能新增 Kernel 方法（应落 User Space + emit / read_ports）。
- 将 Lane B 工具执行塞进 Scheduler「只为对称」。

详见 [execution-model.md](execution-model.md)、[kernel-boundary.md](kernel-boundary.md)。
