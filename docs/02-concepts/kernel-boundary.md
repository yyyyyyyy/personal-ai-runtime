# Kernel 边界

本文档解释 Kernel 边界——系统最重要的架构不变量。它定义了谁能写 governed 数据、谁能直访存储、以及这套规则如何在 CI 中被机器强制。

## GOLDEN RULE

> User Space（API router、agent handler、fragment、前端）永远不直接读写 governed 投影表与 `event_log`。所有访问必须通过 Kernel ABI。

这条规则定义于 [`backend/app/store/table_registry.py`](../../backend/app/store/table_registry.py) 的表分类，由 [`backend/scripts/check_boundary.py`](../../backend/scripts/check_boundary.py) 在 CI 中静态扫描强制。

## 表分类

仓库中的所有业务表必须归入以下两类之一（[`table_registry.py:10-62`](../../backend/app/store/table_registry.py)）。新增表必须在此显式声明，否则 schema 契约测试失败。

### GOVERNED_TABLES（Kernel 投影，事件溯源）

```python
GOVERNED_TABLES = frozenset({
    "event_log",          # 不可变事件日志（真相之源）
    "goals", "actions", "tasks",
    "memories",
    "approvals",
    "conversations", "messages",
    "notifications",
    "projection_checkpoints",  # 增量重建水位
    "handler_executions",      # 执行模型持久化
    "timer_events",
    "policy_events",           # 治理事件溯源根
    "grant_events",            # 能力授权事件溯源根
})
```

这些表是 `event_log` 的纯投影。任何直访（INSERT/UPDATE/DELETE/SELECT）都违规。它们承载「丢失会破坏数据主权」的权威个人事实。

### APP_STORAGE_TABLES（应用存储，可直访）

```python
APP_STORAGE_TABLES = frozenset({
    "events",            # 旧版事件表，已被 event_log 取代，保留迁移用
    "activity_log",      # 人类可读活动日志，event_log 投影派生
    "llm_calls",         # LLM 调用遥测（延迟、token、成本）
    "tool_calls",        # 工具调用遥测；权威记录是 CapabilityInvoked 事件
    "background_tasks",  # 后台任务队列状态（worker scratch view）
    "triggers",          # 触发器定义（用户 UI 自由编辑的应用配置）
    "user_profile",      # 本地偏好，无审计价值
    "inbox_emails",      # IMAP 原始邮件缓存；权威记录是 InboxEmailRecorded 事件
    "app_settings",      # UI 偏好、LLM/Email 连接配置
})
```

[`table_registry.py:28-35`](../../backend/app/store/table_registry.py) 的注释解释了为何每张表**不**做事件溯源：可从权威源重建 / 纯缓存 / 应用本地配置无审计需求。它们永远不得被呈现为「第二个真相之源」。

## Schema 契约

每张 governed 表的预期列集合在 [`table_registry.py:64-119`](../../backend/app/store/table_registry.py) 的 `GOVERNED_SCHEMA` 字典中声明。schema 契约测试通过 `PRAGMA table_info` 校验实际列与契约一致。

## 边界守卫：`check_boundary.py`

[`backend/scripts/check_boundary.py`](../../backend/scripts/check_boundary.py) 是静态扫描器，遍历 `backend/app/` 下所有 `.py`，对 Kernel Space 之外的文件检测三类违规：

1. **DML 写违规** — 在 governed 投影表上匹配 `INSERT INTO|UPDATE|DELETE FROM`。
2. **SELECT 违规** — 在 governed 表上匹配 `SELECT … FROM <table>`。
3. **import 违规** — 在能力子系统白名单之外匹配 `import app.core.harness.mcp_hub`。

Kernel Space 豁免目录：`core/runtime/kernel/`、`store/database.py`（投影读层）、`background_worker.py`（APP_STORAGE 写者）。

已知历史违规记录在 `KNOWN_VIOLATION_ALLOWLIST`（当前为空）。

运行模式：
- 默认：发现新违规即失败（CI 用）
- `--inventory`：列出全部匹配，退出 0
- `--strict`：连 allowlist 中的债也失败

调用：`make boundary` / `make boundary-inventory` / `make boundary-strict`。

## 执行归属守卫：`check_execution_ownership.py`

姊妹脚本 [`backend/scripts/check_execution_ownership.py`](../../backend/scripts/check_execution_ownership.py) 强制 ADR-0007 的执行归属不变量：扫描所有 `kernel.invoke_capability(` 或 `.invoke_capability(` 调用，**任何不含 `execution_id` 参数的调用都失败**。同样有 `BYPASS_ALLOWLIST`、`--inventory`、`--strict` 模式。

调用：`make execution-ownership` / `make execution-ownership-inventory` / `make execution-ownership-strict`。

## 投影溯源守卫：`check_projection_provenance.py`

[`backend/scripts/check_projection_provenance.py`](../../backend/scripts/check_projection_provenance.py) 用 SQL join（而非 schema 变更）验证投影溯源：每条 governed 投影行必须有对应的 `event_log` 事件。验证项：

- `goals` 行（含 `parent_id` 子目标）→ `event_log` 中存在 `(aggregate_type='goal', aggregate_id)` 匹配
- `approvals` 行 → 对应事件
- `handler_executions` 行 → `ExecutionRequested` 事件；若 `event_id` 已设，则 `(event_id, event_seq)` 必须存在于 `event_log`
- `messages.source_event_id` → 必须存在且 `conversation_id` 可追溯
- `conversations` / `actions`（含 `goal_id`）/ `memories` 行 → 对应事件

调用：`make projection-provenance`。详见 [02-concepts/event-sourcing.md](event-sourcing.md)。

## Kernel ABI 暴露面

User Space 通过 `app.core.runtime.kernel_instance` 拿到 Kernel 代理（[`kernel_instance.py`](../../backend/app/core/runtime/kernel_instance.py)），可用方法分三类：

| 类别 | 方法 |
|---|---|
| **写** | `emit_event`、`submit_command`、`invoke_capability`、`request_approval`、`grant_approval`、`deny_approval`、`expire_stale_approvals` |
| **读** | `read_events`、`subscribe_events`、`query_state`、`recall_memory`、`recall_knowledge`、`list_capability_definitions`、`read_work_items`、`recover_work_items` |
| **主权** | `export_event_log_rows`、`import_event_log_rows`、`rebuild`、`rebuild_all`、`save_projection_snapshots` |

`invoke_capability` 是受治理的工具调用入口，详见 [capability-governance.md](capability-governance.md)。

## RuntimeContainer 单例管理

所有 Kernel 级单例由 [`backend/app/core/runtime/runtime_container.py`](../../backend/app/core/runtime/runtime_container.py) 的 `RuntimeContainer` 集中持有（kernel、capability_governance、taint_registry、agent_bus、context_pipeline、fragment_registry、mcp_hub、llm_router、memory_engine、memory_extractor、state_manager、runtime_config）。`runtime.reset()`（[`runtime_container.py:289-305`](../../backend/app/core/runtime/runtime_container.py)）用于测试隔离——清空单例、`taint.reset_external_tools()`、`context_pipeline.reset_source_registry()`。`conftest.py` 的 autouse fixture 在每个测试间调用它。

## Fragment 读边界

Context Fragment（[`backend/app/fragments/`](../../backend/app/fragments/)）通过 [`backend/app/core/runtime/read_ports.py`](../../backend/app/core/runtime/read_ports.py) 暴露的只读端口访问数据，**绝不直访 Kernel 存储**。可用端口：`query_top_active_goals`、`query_recent_inbox_emails`、`retrieve_memory_with_sources`、`search_knowledge`、`query_world_context`、`query_calendar_*`、MCP connector 探针、治理读端口（`query_pending_approval_count`、`query_stagnant_goal_count`）。详见 [context-pipeline.md](context-pipeline.md)。
