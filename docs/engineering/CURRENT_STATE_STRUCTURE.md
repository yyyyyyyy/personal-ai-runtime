# CURRENT_STATE Structure Definition

> 本文档定义 `CURRENT_STATE.md` 的字段结构和含义。
> 不填充任何具体数值——数值填充是 Stage 05 (Reality Sync) 的职责。
>
> **版本：v1.0（基于 Truth Audit 2026-06-30）**

---

## 1. 概述

`CURRENT_STATE.md` 是项目当前可测量状态的快照，由 Stage 05 (Reality Sync) 在每次架构进化循环结束时更新。它与 `TRUTH_AUDIT.md`（Stage 01）配合使用：Truth Audit 提取代码事实，CURRENT_STATE 记录可量化指标。

---

## 2. 字段结构

### 2.1 运行时指标

| 字段 | 类型 | 含义 | 采集方法 | 更新频率 |
|---|---|---|---|---|
| `active_agent_instances` | int | 当前注册的 Agent 实例数 | `agent_registry.list()` | 每次更新 |
| `registered_handlers` | int | HandlerRegistry 中的 handler 数 | `handler_registry.registered_types()` | 每次更新 |
| `scheduler_state` | string | Scheduler 的活跃状态（running/stopped） | RuntimeContainer 检查 | 每次更新 |
| `timer_count` | int | timer_events 投影中的活跃计时器数 | `kernel.query_state("timers")` | 每次更新 |
| `background_tasks_pending` | int | 后台任务队列中待处理的任务数 | `kernel.query_state("background_tasks")` | 每次更新 |
| `mcp_connected_servers` | int | 当前连接的 MCP 外部服务器数 | `mcp_mesh.connected_servers()` | 每次更新 |

### 2.2 代码规模指标

| 字段 | 类型 | 含义 | 采集方法 | 更新频率 |
|---|---|---|---|---|
| `source_files` | int | backend/ 下的 Python 源文件数 | `find backend -name '*.py' \| wc -l` (排除 test) | 每次更新 |
| `source_lines` | int | 源代码总行数 | `cloc` 或 `wc -l` 聚合 | 每次更新 |
| `test_files` | int | 测试文件数 | `find tests -name '*.py' \| wc -l` | 每次更新 |
| `test_lines` | int | 测试代码总行数 | `cloc` 或 `wc -l` 聚合 | 每次更新 |
| `kernel_space_files` | int | Kernel Space (`core/runtime/kernel/`) 下的文件数 | 目录文件计数 | 每次更新 |
| `kernel_space_lines` | int | Kernel Space 代码行数 | `wc -l` | 每次更新 |
| `user_space_files` | int | User Space (除 kernel/ 外的 core/) 下的文件数 | 目录文件计数 | 每次更新 |
| `user_space_lines` | int | User Space 代码行数 | `wc -l` | 每次更新 |

### 2.3 架构概念指标

| 字段 | 类型 | 含义 | 采集方法 | 更新频率 |
|---|---|---|---|---|
| `runtime_concepts_total` | int | 运行时概念总数 | 从 TRUTH_AUDIT 和模块清单计算 | 每次审计后 |
| `core_concepts` | int | Core 分类概念数 | ARCHITECTURE_BUDGET.md §1 | 每次审计后 |
| `supporting_concepts` | int | Supporting 分类概念数 | ARCHITECTURE_BUDGET.md §1 | 每次审计后 |
| `dormant_components` | int | 休眠组件数 | TRUTH_AUDIT DORMANT_COMPONENT 事实 | 每次审计后 |
| `deprecated_components` | int | 废弃但仍存在的组件数 | TRUTH_AUDIT DEAD_CODE 事实 | 每次审计后 |
| `duplication_instances` | int | 代码重复实例数 | TRUTH_AUDIT DUPLICATION 事实 | 每次审计后 |
| `dead_event_types` | int | 声明但永不 emit 的事件类型数 | 事件常量 vs 实际 emit 对比 | 每次审计后 |

### 2.4 治理指标

| 字段 | 类型 | 含义 | 采集方法 | 更新频率 |
|---|---|---|---|---|
| `api_route_groups` | int | 注册的 FastAPI 路由组数 | 从 main.py router 注册计数 | 每次更新 |
| `governed_tables` | int | GOVERNED 表数 | 从 schema_ddl.py 或 table_registry.py 读取 | 每次更新 |
| `app_storage_tables` | int | APP_STORAGE 表数 | 从 schema_ddl.py 或 table_registry.py 读取 | 每次更新 |
| `builtin_tool_categories` | int | builtin 工具类别数 | `mcp_hub` 注册方法计数 | 每次更新 |
| `builtin_tool_count` | int | builtin 工具总数 | `len(mcp_hub._tools)` - external | 每次更新 |
| `context_fragments` | int | 注册的 Context Fragment 数 | FragmentRegistry 计数 | 每次更新 |
| `ci_gates` | int | CI 强制执行的架构门禁数 | CI 脚本计数 | 每次更新 |

### 2.5 质量指标

| 字段 | 类型 | 含义 | 采集方法 | 更新频率 |
|---|---|---|---|---|
| `coverage_runtime` | float | 运行时代码覆盖率 (%) | pytest-cov 输出 | 每次 CI |
| `coverage_api` | float | API 代码覆盖率 (%) | pytest-cov 输出 | 每次 CI |
| `mypy_errors` | int | mypy 类型检查错误数 | `mypy backend/` 输出 | 每次 CI |
| `ruff_errors` | int | ruff lint 错误数 | `ruff check backend/` 输出 | 每次 CI |
| `test_count` | int | 测试用例总数 | pytest --collect-only 计数 | 每次 CI |
| `test_pass_rate` | float | 测试通过率 (%) | pytest 最后一次运行结果 | 每次 CI |

### 2.6 部署指标

| 字段 | 类型 | 含义 | 采集方法 | 更新频率 |
|---|---|---|---|---|
| `python_version` | string | Python 版本 | `python -V` | 每次更新 |
| `dependencies_count` | int | pip 依赖数 | `pip list \| wc -l` | 每次更新 |
| `alembic_head` | string | Alembic 迁移最新版本 | `alembic heads` | 每次更新 |
| `docker_image_size` | string | Docker 镜像大小 | `docker images` 或构建日志 | 每次构建 |

### 2.7 宪法规约指标

| 字段 | 类型 | 含义 | 采集方法 | 更新频率 |
|---|---|---|---|---|
| `invariant_count` | int | CONSTITUTION 定义的不可违反规则数 | CONSTITUTION.md §3 计数 | 每次宪法更新 |
| `invariant_verified` | int | 有 CI 验证的不可违反规则数 | INVARIANTS.md 交叉验证 | 每次审计 |
| `adr_count` | int | 架构决策记录数 | CONSTITUTION.md §5 计数 | 每次宪法更新 |
| `known_arch_debt` | int | 已知架构债务项数 | ARCHITECTURE.md §9 计数 | 每次审计 |
| `constitution_version` | string | 宪法版本号 | CONSTITUTION.md 头部 | 每次宪法更新 |

---

## 3. 采集频率说明

| 频率 | 适用指标 | 说明 |
|---|---|---|
| 每次 CI | coverage_*, mypy_errors, ruff_errors, test_* | 随代码提交自动更新 |
| 每次审计后 | runtime_concepts_*, dormant/deprecated/duplication/dead_* | 仅在 Stage 01 Truth Audit 后更新 |
| 每次宪法更新 | invariant_count, adr_count, constitution_version | 随 Stage 02 Constitution Update 更新 |
| 每次构建 | docker_image_size | 随 Docker 构建更新 |
| 按需 | active_agent_instances, scheduler_state, timer_count 等 | 运行时状态指标，随时可通过 API 查询 |

---

## 4. 数据来源

| 类别 | 主数据源 | 辅助数据源 |
|---|---|---|
| 运行时指标 | RuntimeContainer + 投影查询 | API 端点 |
| 代码规模 | 文件系统扫描 (`find`, `cloc`) | `wc -l` |
| 架构概念 | `TRUTH_AUDIT.md` | `ARCHITECTURE_BUDGET.md` |
| 治理指标 | 代码扫描 + 配置文件 | CI 脚本 |
| 质量指标 | pytest-cov, mypy, ruff | CI 日志 |
| 部署指标 | pip, alembic, docker | 构建日志 |
| 宪法规约 | `CONSTITUTION.md` | `INVARIANTS.md` |

---

## 5. 禁止行为

- 不在本文件中填入任何实际数值
- 不修改本文件中的字段定义（除非宪法更新 Stage 02 重新授权）
- 不添加未在 CONSTITUTION 或 ARCHITECTURE_BUDGET 中定义的指标维度
