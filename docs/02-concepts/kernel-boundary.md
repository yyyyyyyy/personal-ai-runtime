# Kernel 边界

本文档解释 Kernel 边界——系统最重要的架构不变量。它定义了谁能写 governed 数据、谁能直访存储、以及这套规则如何在 CI 中被机器强制。

职责上的 Runtime / Product 划分见 [architecture-principles.md](architecture-principles.md)；本文专注**表级与 ABI 级**边界。

## GOLDEN RULE

> User Space（API router、Product 模块、agent handler、fragment、前端）永远不直接读写 governed 投影表与 `event_log`。所有访问必须通过 Kernel ABI。

这条规则定义于 [`backend/app/store/table_registry.py`](../../backend/app/store/table_registry.py) 的表分类，由 [`backend/scripts/check_boundary.py`](../../backend/scripts/check_boundary.py) 在 CI 中静态扫描强制。

## Runtime / Product 与本边界的关系

- **Kernel 边界**回答：谁能碰 governed 存储。
- **Runtime / Product 边界**回答：谁拥有机制、谁拥有领域策略。

二者正交：Product 代码必须遵守 GOLDEN RULE；落在 `core/` 下的领域工具实现仍是 Product 职责，不应因目录位置获得直访 governed 表的特权。

## 表分类

仓库中的所有业务表必须归入以下两类之一（[`table_registry.py`](../../backend/app/store/table_registry.py)）。新增表必须在此显式声明，否则 schema 契约测试失败。

### GOVERNED_TABLES（Kernel 投影，事件溯源）

```python
GOVERNED_TABLES = frozenset({
    "event_log",          # 不可变事件日志（真相之源）
    "work_items",         # v1.0：统一 task + action + goal
    "memories",
    "approvals",
    "conversations", "messages",
    "notifications",
    "projection_checkpoints",
    "handler_executions",
    "timer_events",
    "policy_events",
    "inbox_emails",
    "tool_calls",
    "llm_calls",
})
```

目标行在 `work_items` 中（`work_type='goal'`），用 `query_state("work_items", work_type="goal", ...)` 读取，无独立 `goals` selector。

### APP_STORAGE_TABLES（应用存储，可直访）

```python
APP_STORAGE_TABLES = frozenset({
    "activity_log",
    "background_tasks",
    "user_profile",
    "app_settings",
    "memory_index_repairs",
})
```

[`table_registry.py`](../../backend/app/store/table_registry.py) 的注释解释了为何每张表**不**做事件溯源。

## Schema 契约

每张 governed 表的预期列集合在 [`table_registry.py`](../../backend/app/store/table_registry.py) 的 `GOVERNED_SCHEMA` 字典中声明。schema 契约测试通过 `PRAGMA table_info` 校验实际列与契约一致，**同时在 raw DDL 路径与 Alembic 生产路径各跑一遍**（[`test_projection_schema_contract.py`](../../backend/tests/runtime/test_projection_schema_contract.py)）。

## 边界守卫：`check_boundary.py`

[`backend/scripts/check_boundary.py`](../../backend/scripts/check_boundary.py) 是静态扫描器，遍历 `backend/app/` 下所有 `.py`，对 Kernel Space 之外的文件检测三类违规：

1. **DML 写违规** — 在 governed 投影表上匹配 `INSERT INTO|UPDATE|DELETE FROM`。
2. **SELECT 违规** — 在 governed 表上匹配 `SELECT … FROM <table>`。
3. **import 违规** — 在能力子系统白名单之外匹配 `import app.core.harness.mcp_hub`。

调用：`make boundary` / `make boundary-inventory` / `make boundary-strict`。

## 执行归属守卫：`check_execution_ownership.py`

[`backend/scripts/check_execution_ownership.py`](../../backend/scripts/check_execution_ownership.py) 强制所有 `invoke_capability(` 调用必须含 `execution_id` 参数。

## 投影溯源守卫：`check_projection_provenance.py`

[`backend/scripts/check_projection_provenance.py`](../../backend/scripts/check_projection_provenance.py) 用 SQL join 验证投影溯源：

- `approvals` 行 → 对应 `event_log` 事件
- `handler_executions` 行 → `ExecutionRequested` 事件
- `messages.source_event_id` → 必须存在且 `conversation_id` 可追溯
- `conversations` / `memories` / `work_items` 行 → 对应事件

## Kernel ABI 暴露面

User Space 通过 `app.core.runtime.kernel_instance` 拿到 Kernel 代理，可用方法分三类：

| 类别 | 方法 |
|---|---|
| **写** | `emit_event`、`submit_command`、`invoke_capability`、`request_approval`、`grant_approval`、`deny_approval`、`expire_stale_approvals` |
| **读** | `read_events`、`subscribe_events`、`query_state`、`count_state`、`recall_memory`、`recall_knowledge`、`list_capability_definitions`、`read_scheduled_executions`、`recover_scheduled_executions` |
| **主权** | `export_event_log_rows`、`import_event_log_rows`、`rebuild`、`rebuild_all`、`save_projection_snapshots` |

目标数据通过 `query_state("work_items", work_type="goal", ...)` / `count_state(...)` 读取（`goals` selector 已移除）。`read_work_items` / `recover_work_items` 仍是 ScheduledExecution 读路径的兼容别名。

## Fragment 读边界

Context Fragment 通过 [`backend/app/core/runtime/read_ports/__init__.py`](../../backend/app/core/runtime/read_ports/__init__.py) 暴露的只读端口访问数据，**绝不直访 Kernel 存储**。详见 [context-pipeline.md](context-pipeline.md)。
