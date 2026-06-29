# GOVERNANCE

> Context 选择与组装的运行时治理层。
>
> 架构总览见 [ARCHITECTURE.md](ARCHITECTURE.md)，Context Fragment 设计见该文档 §6。

---

## 职责边界

Runtime Governance 负责 **在编译 Prompt 之前** 决定加载哪些 Context Fragment，并将选中 Fragment 组装为上下文字符串。

| 模块 | 路径 | 职责 |
|------|------|------|
| **CompileRequest / CompilePlan** | `app/core/runtime/governance/context_policy.py` | 编译请求与策略输出 |
| **ContextPolicy** | 同上 | 将请求评估为计划（选择决策所有者） |
| **DefaultContextPolicy** | 同上 | 默认策略：复现 QueryAnalyzer + FragmentSelector 行为 |
| **ContextPipeline** | `app/core/runtime/governance/context_pipeline.py` | 执行 CompilePlan → 组装（非决策所有者） |
| **QueryAnalyzer** | `app/core/runtime/governance/query_analyzer.py` | 意图标签（DefaultPolicy 内部使用） |
| **FragmentSelector** | `app/core/runtime/governance/fragment_selector.py` | 三层 Fragment 选择（DefaultPolicy 内部使用） |

Chat 层仅保留 **Prompt 编译**：

| 模块 | 路径 | 职责 |
|------|------|------|
| **PromptCompiler** | `app/chat/prompt_compiler.py` | 静态指令（Prompt Artifact）+ Context Pipeline → 最终 system prompt |
| **PromptArtifactLoader** | `app/chat/prompt_artifact.py` | 加载静态系统指令 |

---

## 数据流

```text
CompileRequest
    → ContextPolicy.evaluate()     → CompilePlan (selected_fragments, budget, analysis)
    → ContextAssembler.assemble()  → context string
    → PromptCompiler.compile()     → artifact + context → system prompt
```

---

## Context Policy（Runtime Primitive）

Policy 拥有 **选择决策**；Pipeline 是 **策略执行器**。

| 类型 | 字段 / 行为 |
|------|-------------|
| **CompileRequest** | `user_message`, `conversation_id`, `execution_id`, `stage`, `principal`, `context_budget` |
| **CompilePlan** | `selected_fragments`, `context_budget`, `policy_name`, `analysis_result`, `stage`, `selected_fragment_ids`, `rationale` |
| **DefaultContextPolicy** | `policy_name="default"`；按 `stage` 选择 Fragment 集 |

### Stage 矩阵（DefaultContextPolicy）

| Stage | Fragment 选择 | Budget | 说明 |
|-------|--------------|--------|------|
| **chat** | Core + Priority + Scenario | 请求值（默认 32000） | 默认对话上下文 |
| **post_tool** | `core.memory`, `core.conversation_state` + Scenario | min(请求, 24000) | 工具执行后续航 |
| **brief** | `core.goals`, `core.reviews`, `core.world`, `calendar.*` | min(请求, 16000) | 简报/摘要 |

`principal` 字段存在于 CompileRequest，但 **尚未** 参与选择。

### CompileRequest 生命周期

```text
入口 → CompileRequest → DefaultContextPolicy.evaluate → CompilePlan → ContextAssembler

LLM 路径（含 Prompt Artifact）:
  chat_handler (stage=chat)
  brain_completion / approval resume (stage=post_tool)
    → PromptCompiler.compile → ContextPipeline.build(stage=...)
```

### Policy Coverage Matrix

| 入口 | 模块 | Stage | 经 Policy | 输出 |
|------|------|-------|-----------|------|
| `ChatRequested` | `chat_handler.py` | `chat` | ✓（经 PromptCompiler → Pipeline） | system prompt → Brain |
| Approval resume / tool loop | `brain_completion.py` | `post_tool` | ✓（经 PromptCompiler → Pipeline） | system prompt → Brain |

**非 Policy 路径（有意排除）：**

| 路径 | 原因 |
|------|------|
| `brain_completion._synthesize_from_tool_results` | 工具上限兜底，复用已有 messages，不重新选 Fragment |
| `intent_predictor.pre_fetch` | 主动预取元数据，非 Prompt 编译 |

架构测试：`tests/test_policy_coverage.py`

---

## Fragment 选择策略（chat stage — DefaultContextPolicy 内部）

`FragmentSelector` 三层策略：

1. **Core Tier** — `core.memory`, `core.actions`, `core.events`, `core.goals` 始终加载
2. **Priority Tier** — `priority >= 80` 的 Universal Fragment
3. **Scenario Tier** — 意图标签 → Scenario Fragment 映射

---

## Read Boundary

Fragment 是 Context Adapter，不是 Repository。所有数据读取经 **Read Ports** 进入 Kernel：

```text
Fragment → app/core/runtime/read_ports.py → Kernel.query_state / recall_* → Projection
```

| Read Port | Kernel 接口 |
|-----------|-------------|
| `query_pending_actions` | `query_state("actions", ...)` |
| `query_top_active_goals` | `query_state("goals", status_in=...)` |
| `query_recent_reviews` | `query_state("reviews", ...)` |
| `query_conversation_messages` | `query_state("messages", ...)` |
| `query_recent_inbox_emails` | `query_state("inbox_emails", ...)` |
| `search_inbox_emails` | `query_state("inbox_emails", search=...)` |
| `retrieve_memory_context` | `kernel.recall_memory` + projection enrich |
| `search_knowledge` | `kernel.recall_knowledge` |
| `query_world_context` | `world_model`（内部使用 `query_state`） |
| `query_calendar_*` | MCP calendar server（外部数据源） |

架构测试：`tests/test_fragment_read_boundary.py`（INV-R1，AST 扫描）

---

## 已知技术债

- **principal 感知策略** — CompileRequest.principal 未参与 Fragment 选择
- **Capability Policy 联动** — Context 选择与 Capability 授权独立
- **Execution 感知策略** — Policy 不读取 ExecutionContext / Event Log 动态裁剪
- **可替换 Policy 注册** — 仅 DefaultContextPolicy 单实现

---

## 依赖方向

```text
Chat (PromptCompiler)
  └─ depends on → Runtime Governance (ContextPipeline)
                    └─ depends on → ContextPolicy (DefaultContextPolicy)
                          └─ uses internally → QueryAnalyzer, FragmentSelector
                    └─ depends on → Context Runtime (FragmentRegistry, RuntimeContext)
                    └─ depends on → Assembler (ContextAssembler)
                    └─ depends on → Fragments (register_all_fragments)

Governance MUST NOT depend on Chat.
```

---

## 相关文档

- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构总览与 Context 编译层
- [NORTH_STAR](../engineering/NORTH_STAR.md) — 产品宪法
- [INVARIANTS](../engineering/INVARIANTS.md) — 可验证规则
