# 开发者指南

> 面向想扩展 Runtime 能力的开发者：添加新工具、新 Context Fragment、新 Agent Handler。
>
> 本项目的工程目标是让 AI 换模型不丢记忆。以下文档描述技术如何支撑这一承诺。

---

## 目录

1. [架构速览](#1-架构速览)
2. [添加一个新 Tool](#2-添加一个新-tool)
3. [添加一个 Context Fragment](#3-添加一个-context-fragment)
4. [添加一个 Agent Handler](#4-添加一个-agent-handler)
5. [Runtime 不变量与 CI](#5-runtime-不变量与-ci)
6. [技术栈摘要](#6-技术栈摘要)
7. [调试与常见问题](#7-调试与常见问题)

---

## 1. 架构速览

Personal AI Runtime 的核心目标是让 AI 的记忆和状态独立于任何模型。技术上通过 Event Sourcing 实现：所有交互以不可变事件记录，状态从事件推导。

核心分层：

```text
API 层 (FastAPI routes)
    ↓ emit_event / invoke_capability
Runtime Kernel (Event Log + Projections + CapabilityGateway)
    ↓
Agent 子系统 (AgentBus → Scheduler → Handler)
    ↓
Context 编译层 (Fragment + ContextPolicy → LLM Prompt)
    ↓
Harness (MCP Hub: 内置工具 + 外部 MCP Mesh)
```

关键概念：

- **Event Log**：只追加、不可变。所有状态变更先写事件，再由 Projector 物化到投影表
- **Projection**：Event Log 的物化视图（如 `goals`、`memories`、`approvals`），可 `rebuild` 重建
- **GOVERNED_TABLES**：Kernel 写入的投影表（event_log + projections），CI `check_boundary.py` 强制
- **APP_STORAGE_TABLES**：允许应用直写的运营/缓存表（如 `inbox_emails`、`llm_calls`）
- **CapabilityGateway**：4 道闸门（forbidden → fail-closed → pre-approved → risk+taint）

详细架构见 [ARCHITECTURE](../architecture/ARCHITECTURE.md)。

---

## 2. 添加一个新 Tool

工具是 AI Agent 可调用的能力。内置工具注册在 `backend/app/core/harness/mcp_hub.py`。

### 2.1 注册工具

```python
# 在 mcp_hub.py 的对应 _register_*_tools() 方法中添加
self.register_tool(ToolDef(
    name="my_new_tool",
    description="对 AI 描述这个工具的功能",
    parameters={
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "参数说明"
            }
        },
        "required": ["param1"]
    },
    handler=my_handler_function,
))
```

### 2.2 编写 Handler

```python
# 新建 backend/app/core/harness/builtin_tools/my_tool.py
import json

async def my_handler(params: dict) -> str:
    value = params["param1"]
    return json.dumps({"result": value})
```

### 2.3 配置策略

在 `backend/capability_policy.json` 中为新工具分配风险等级：

```json
{
  "auto_allow": ["my_new_tool"],
  "needs_user": ["write_file"],
  "forbidden": []
}
```

一个工具只能出现在一个列表中。CI 强制检查覆盖完整性。

### 2.4 考虑 Taint

如果工具会从外部获取内容（网页、邮件），标记为摄入工具：

```python
from app.core.runtime.taint import register_external_ingestion_tool
register_external_ingestion_tool("my_new_tool")
```

这确保同一 `correlation_id` 上的写类工具被自动升级审批，防止 Prompt Injection。

---

## 3. 添加一个 Context Fragment

Fragment 是 LLM 上下文的一个只读数据源。所有 Fragment 的数据获取必须通过 **Read Ports**，不得直接访问数据库。

### 3.1 创建 Fragment 类

```python
# backend/app/fragments/custom/my_fragment.py
from app.context_runtime import ContextFragment, RuntimeContext, FragmentResult

class MyCustomFragment(ContextFragment):

    @property
    def id(self) -> str:
        return "custom.my_feature"

    @property
    def priority(self) -> int:
        return 75

    @property
    def tags(self) -> list[str]:
        return ["custom", "feature"]

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        from app.core.runtime.read_ports import query_some_data
        data = query_some_data(limit=10)
        content = f"## My Feature\n{self._format(data)}"
        return FragmentResult(content=content)

    def _format(self, data) -> str:
        return "\n".join(f"- {item}" for item in data)
```

### 3.2 注册 Fragment

在 `backend/app/fragments/register.py` 中添加：

```python
from app.fragments.custom.my_fragment import MyCustomFragment

_ALL_FRAGMENT_CLASSES = [
    # ... 已有 fragment ...
    MyCustomFragment,
]
```

### 3.3 Fragment 选择策略

`DefaultContextPolicy` 按三层选择 Fragment：

1. **Core Tier**：始终加载（memory、actions、events、goals、reviews）
2. **Priority Tier**：`priority >= 80` 的 fragment
3. **Scenario Tier**：根据 `QueryAnalyzer` 的意图标签匹配对应 tags

---

## 4. 添加一个 Agent Handler

Handler 是响应特定事件类型的业务逻辑函数。

### 注册 Handler

```python
from app.core.runtime.handler_registry import subscribe

@subscribe("MyEvent")
async def on_my_event(ctx: ExecutionContext, event: Event):
    """处理 MyEvent 事件。"""
    await ctx.emit("SomethingHappened", "my_aggregate", event.aggregate_id,
                   payload={"detail": "processed"}, caused_by=event.id)
```

### ExecutionContext 要点

- `ctx.execution_id`：当前执行的唯一标识
- `ctx.principal`：执行者身份（agent / user / system）
- `ctx.emit(...)`：写入 Event Log
- 调用能力必须通过 `kernel.invoke_capability()` 并携带 `execution_id`

---

## 5. Runtime 不变量与 CI

### 测试命令

```bash
make test-backend        # pytest -m "not live_llm"
make lint                # ruff check
make typecheck           # mypy app/ scripts/
make ci-local            # lint + typecheck + test + boundary + ownership + rebuild + export
```

### 关键 CI 守卫

| 脚本 | 守护内容 |
|------|----------|
| `check_boundary.py` | User Space 不得 DML GOVERNED 表 |
| `check_execution_ownership.py` | `invoke_capability` 须传 `execution_id` |
| `check_projection_provenance.py` | projections join event_log |
| `verify_rebuild.py` | 12 张投影表事件重建 |
| `verify_vector_consistency.py` | SQLite 与 Chroma ID 一致性 |

### 添加新表

新增业务表必须在 `table_registry.py` 中显式归类为 `GOVERNED_TABLES` 或 `APP_STORAGE_TABLES`。CI 强制检查。

---

## 6. 技术栈摘要

| 层 | 技术 | 位置 |
|----|------|------|
| 后端框架 | Python 3.12, FastAPI, uvicorn | `backend/app/main.py` |
| Schema / 迁移 | Alembic + 手写 SQL DDL | `backend/app/store/` |
| 存储 | SQLite (WAL), ChromaDB | `backend/app/store/` |
| LLM | OpenAI 兼容 API (DeepSeek) | `backend/app/config.py` |
| Agent | AgentBus + Scheduler + WorkItem | `backend/app/core/runtime/` |
| MCP | 内置工具 + 外部 MCP Mesh | `backend/app/core/harness/` |
| 前端 | React 19, TypeScript, Vite, Tailwind | `frontend/src/` |
| 桌面 | Electron 33 | `desktop/` |
| 测试 | Pytest, Vitest, Playwright | `backend/tests/`, `frontend/e2e/` |

---

## 7. 调试与常见问题

### 运行单个测试

```bash
cd backend
python3 -m pytest tests/runtime/test_event_sourcing.py::test_event_log_is_append_only -xvs
```

### 检查 CI 失败

运行 `make ci-local` 获取与 CI 一致的反馈。常见失败：

- `boundary check`：代码中直接 DML 了 GOVERNED 表。必须改用 `kernel.emit_event()`。
- `ownership check`：`invoke_capability` 调用未传 `execution_id`。
- `rebuild verify`：投影表中有绕过事件流的直接写入。

### 检查真实数据

```bash
cd backend && python3 scripts/verify_vector_consistency.py --check-default
```

### 查看 Event Log

```bash
cd backend
python3 -c "from app.store.database import get_db; conn = get_db(); rows = conn.execute('SELECT seq, event_type, aggregate_type FROM event_log ORDER BY seq DESC LIMIT 20').fetchall(); [print(r) for r in rows]"
```
