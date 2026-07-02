# 扩展指南

本文档列出代码中可观察到的所有扩展点——在何处插入新行为而不破坏架构不变量。每个扩展点都附 CI 守卫提醒。

## 扩展点总览

| 类型 | 位置 | CI 守卫 |
|---|---|---|
| 投影器 | `kernel/projectors_*.py` + `projectors_registry._OWNED_TABLES` | `check_projection_provenance.py`、`verify_rebuild.py` |
| 事件 handler | `@subscribe("EventType")` 装饰器 | 无静态守卫；运行时由 Scheduler 执行 |
| Context Fragment | `app/fragments/register.py` | `check_boundary.py`（必须用 read_ports） |
| 外部 MCP server | `backend/mcp_config.json` | 无 |
| 内建工具 | `core/harness/builtin_tools/` + `mcp_hub._register_*_tools` | `check_boundary.py`、capability 治理 |
| LLM provider | runtime_config（DB）或 env | 无 |
| 通知通道 | `core/runtime/notification_channel.py` | 无 |
| 工具后处理规则 | `core/agents/tool_postprocess.py` | 无 |
| Runtime 子系统单例 | `core/runtime/runtime_container.py` | `runtime.reset()` 测试隔离 |

## 投影器：新增投影

为事件类型添加投影：

1. 在 [`backend/app/core/runtime/kernel/projectors_*.py`](../../backend/app/core/runtime/kernel/) 添加函数：

```python
@projector("YourEventType")
def project_your_event(event, conn):
    conn.execute("INSERT INTO your_table (...) VALUES (...)", {...})
```

2. 在 [`projectors_registry.py`](../../backend/app/core/runtime/kernel/projectors_registry.py) 的 `_OWNED_TABLES` 注册：

```python
_OWNED_TABLES["your_aggregate_type"] = ["your_table"]
```

这样 `kernel.rebuild("your_aggregate_type")` 才能正确清空并重建。

3. 若新增 governed 表，在 [`backend/app/store/table_registry.py`](../../backend/app/store/table_registry.py) 的 `GOVERNED_TABLES` 添加表名，并在 `GOVERNED_SCHEMA` 声明预期列。

4. Alembic migration 创建表（[`backend/alembic/versions/`](../../backend/alembic/versions/)）。

**守卫**：`check_projection_provenance.py` 验证每条投影行有对应 event_log 事件；`verify_rebuild.py` 验证全量重建字节一致；`check_boundary.py` 阻止 User Space 直访新表。

## 事件 Handler

订阅事件类型：

```python
from app.core.runtime.handler_registry import subscribe

@subscribe("YourEventType")
async def handle_your_event(ctx: ExecutionContext, event: Event) -> None:
    ...
```

Handler 签名 `(ExecutionContext, Event) → None`。`ExecutionContext` 暴露 `instance_id`、`actor`、`correlation_id`、`_kernel`、`principal`、`execution_id`、`emit()`。模块须在启动时被 import（如 `mvp/__init__.py`）才能注册。

## Context Fragment

添加上下文片段：

1. 子类化 `ContextFragment`（[`backend/app/context_runtime.py:43-69`](../../backend/app/context_runtime.py)）：

```python
class YourFragment(ContextFragment):
    id = "your.id"
    priority = 60
    max_tokens = 1000
    tags = {"your_tag", "universal"}

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        content = ...  # 必须通过 read_ports 访问数据
        return FragmentResult(content=content, token_count=..., sources=[...])
```

2. 在 [`backend/app/fragments/register.py:46-53`](../../backend/app/fragments/register.py) 注册：

```python
fragment_registry.register(YourFragment())
```

**强制**：必须通过 [`backend/app/core/runtime/read_ports.py`](../../backend/app/core/runtime/read_ports.py) 访问数据，绝不直访 Kernel 存储——`check_boundary.py` 与 `test_fragment_read_boundary.py` 强制。`priority >= 100` 的 fragment 永不被 Assembler 丢弃。

## 外部 MCP Server

在 [`backend/mcp_config.json`](../../backend/mcp_config.json) 的 `external_servers` 添加条目：

```json
{
  "name": "your-server",
  "type": "stdio",
  "enabled": true,
  "startup_connect": true,
  "command": "npx",
  "args": ["-y", "your-mcp-package"],
  "policy_default": "auto_allow",
  "needs_user_tools": ["dangerous_tool"],
  "ingestion_tools": ["fetch_tool"],
  "required_env": ["YOUR_API_KEY"],
  "connect_timeout_seconds": 10,
  "call_timeout_seconds": 30
}
```

同步更新 [`backend/mcp_registry.json`](../../backend/mcp_registry.json)（UI marketplace 元数据：中文描述、类别、安装命令、环境变量提示）与 [`.env.example`](../../.env.example)。重启后端生效。详见 [`backend/prompts/coding_rules.md`](../../backend/prompts/coding_rules.md) 的配方。

## 内建工具

1. 在 [`backend/app/core/harness/builtin_tools/`](../../backend/app/core/harness/builtin_tools/) 新建模块，暴露 `*_server` 对象与 handler 函数。
2. 在 [`mcp_hub.py`](../../backend/app/core/harness/mcp_hub.py) 添加 `_register_your_tools` 方法，在 `__init__` 调用，注册 `ToolDef`（写工具设 `requires_confirmation=True`）。
3. 在 [`backend/capability_policy.json`](../../backend/capability_policy.json) 分类（auto_allow / needs_user / forbidden）。
4. 若属摄入类或写类，在 [`backend/app/core/runtime/taint.py`](../../backend/app/core/runtime/taint.py) 的 `_BUILTIN_EXTERNAL_INGESTION_TOOLS` 或 `WRITE_CLASS_TOOLS` 注册。

**守卫**：capability 治理 4-gate；CI 内联检查期望 26 个命名内建工具。

## LLM Provider

经 UI `/settings` 或 `PUT /api/settings/llm` 添加（持久化到 `app_settings` DB）：

- `provider_type` ∈ `openai_compatible`、`ollama`
- `preset` ∈ `deepseek`、`openai`、`anthropic`、`ollama`（或自定义）
- `api_key`、`base_url`、`model`、`enabled`

`update_llm_config` 后调 `llm_router.reload()` 重建。Failover 自动尝试 `[primary, *fallbacks]`。

## 通知通道

子类化 `BaseChannel`（[`backend/app/core/runtime/notification_channel.py`](../../backend/app/core/runtime/notification_channel.py)），添加到 `NotificationRouter`。现有实现：`DesktopChannel`（WS 广播）、`WebhookChannel`（HTTP POST）、`NtfyChannel`（ntfy.sh）。经 `/api/settings/notifications` 配置 webhook_url / ntfy_topic / ntfy_server。

## 工具后处理规则

在 [`backend/app/core/agents/tool_postprocess.py`](../../backend/app/core/agents/tool_postprocess.py) 注册：

```python
register_rule("your_tool", ToolPostprocessRule(
    compact_for_llm=...,
    canned_summary=...,   # 可短路工具循环
    prompt_hint=...,
))
```

当前注册：`check_inbox`、`read_inbox_email`。

## Runtime 子系统单例

添加新子系统到 [`backend/app/core/runtime/runtime_container.py`](../../backend/app/core/runtime/runtime_container.py)：

1. 添加私有 attr 并在 `_SINGLETON_ATTRS`（[`runtime_container.py:274`](../../backend/app/core/runtime/runtime_container.py)）登记。
2. 添加 `@property` 返回 `_LazyProxy(lambda: self._your_subsystem)`。
3. `reset()`（[`runtime_container.py:289-305`](../../backend/app/core/runtime/runtime_container.py)）会自动清空——保证测试隔离。

`_LazyProxy`（[`runtime_container.py:39-83`](../../backend/app/core/runtime/runtime_container.py)）透明转发 `__getattr__`，但 `__setattr__` 让 mock 留在 proxy 本地。

## 扩展时的 CI 检查清单

变更后务必本地跑：

```bash
make ci-local                    # 全套
make boundary                    # 新表/新 import 没违规
make execution-ownership         # 新 invoke_capability 带 execution_id
make projection-provenance       # 新投影行有溯源
make rebuild-verify              # 重建字节一致
make vector-consistency-verify   # 向量对账
```

详见 [testing.md](testing.md)。
