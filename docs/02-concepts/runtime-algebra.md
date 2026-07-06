# Runtime Algebra

本文档定义 Personal AI Runtime 的**最小公理系统**。它不是描述"现在有什么"，而是定义"一切应该能推导回什么"。

它的目的是：

- 成为所有增加/删除概念的判据
- 防止 Framework Disease（通过不断增加抽象来扩展）
- 确保 Runtime 的核心概念数单调下降

> **Runtime 通过组合原语来扩展；Framework 通过增加概念来扩展。本文档存在的唯一目的，是确保这个项目走前者的路。**

---

## 1. 五个原语

任何不在以下五者之中的概念，要么是组合，要么是多余的。

```
EVENT   — 不可变事实（已发生、不可撤销）
STATE   — Event 的物化视图（可以从 Event 重建）
CAPABILITY — 受治理的工具调用（身份 + 授权 + 审计）
WORK    — 待执行的计算单元（有生命周期、可重试、可归属）
CONTEXT — 触发 WORK 的输入（消息 + 环境快照）
```

### 1.1 Event

**定义**：描述已发生事实的不可变记录。唯一写入入口是 `Kernel.emit_event()`。

**不变量**：

- `event_log` 是 append-only（SQLite 触发器强制）
- Event 一旦写入，payload 不可篡改
- 全部 STATE 都可以从 Event 重放重建

**它能表达什么**：

- 用户动作：`GoalCreated`、`MemoryUpdated`、`MessageAppended`
- 系统动作：`TimerFired`、`ExecutionStarted`、`CapabilityInvoked`
- 业务状态转换：所有 `XxxCreated/Updated/Deleted` 系列

**它不是什么**：

- **不是**流式内容（token delta 不入 event_log）
- **不是**请求的即时响应（请求和完成是两个独立 Event）
- **不是**RPC（`submit_command` 是 Event 上的同步包装，不是新原语）

### 1.2 State

**定义**：Event 的物化视图。State 存在于 governed 投影表（`goals`、`memories`、`conversations` 等），由 projector 从 event_log 同步投影。

**不变量**：

- State 必须可从 Event 完整重建（`kernel.rebuild_all()` 验证）
- 所有 governed 投影表写入通过 Kernel 的 `projectors.apply(event, conn)`
- 读操作通过 `kernel.query_state(selector)` 或未来的 Repository 端口

**它能表达什么**：

- 聚合的当前视图：`goals` 表、`memories` 表、`notifications` 表
- 向量索引：ChromaDB 是 memories 的派生索引（非独立 State）
- 配置文件快照：`app_settings` 是 local config 的物化

**它不是什么**：

- **不是**缓存（APP_STORAGE 表可以直访，不需要事件溯源）
- **不是**中间计算结果（那些属于 WORK 的执行过程，不进事件日志）

### 1.3 Capability

**定义**：以受治理方式执行外部效果的能力。所有工具调用（内置 + MCP）的唯一入口是 `Kernel.invoke_capability()`。

**不变量**：

- 4-gate 授权：forbidden → principal grant → pre-approved → risk assessment
- 所有工具调用产生可审计事件：`CapabilityInvoked/Failed/Denied/Deferred`
- 外部摄入类工具污染当前 `correlation_id`（taint 追踪）

**它能表达什么**：

- 读取：`web_search`、`check_inbox`、`list_calendar_events`（auto_allow）
- 写入：`write_file`、`send_email`、`shell_exec`（needs_user）
- 组合：`fetch_url`（摄入） → `write_file`（污染后强制 high risk）
- Agent 授权：`grant_events` 投影控制哪些 principal 能调哪些 Capability

### 1.4 Work

**定义**：需要被执行的计算单元。有生命周期（pending → running → completed/failed）、可重试（max_retries + delay）、可归属（`execution_id` → `handler_executions` 行）。

**当前分裂**：

```
Goal / Task / Action / Execution / BackgroundTask
```

这五个概念**本质是同一个东西**——只是 status 和 metadata 不同：

| 概念 | 本质 | 多余原因 |
|---|---|---|
| Goal    | 带 deadline + tree 的 Work | `parent_id` 即可 |
| Task    | 带 dependency 的 Work | `dependencies_json` 列即可 |
| Action  | Goal 的子 Work | 与 Task 语义重叠 |
| Execution | Work 的执行记录 | 应是 Work 的一个 lifecycle 阶段 |
| BackgroundTask | 带 plan_json 的 Work | 可以是一个字段 |

**合并后**：唯一的 `Work` 原语，带 type 标签（goal/task/action/background）和 lifecycle status（pending/running/completed/failed/retrying）。不损失任何语义，只删除重复的投影表和事件类型。

**不变量**：

- 所有 Work 执行必须绑定 `execution_id`
- 中断恢复：从 `handler_executions` 投影重建
- Work 的状态转换通过 Event（`ExecutionRequested → Started → Completed/Failed → Retried`）

### 1.5 Context

**定义**：触发 Work 执行的输入快照。一次 chat turn 的 Context = user_message + 预编译的 system_prompt（fragment 组装结果）。

**不变量**：

- Fragment 是 Context 的**生产函数**，不是独立原语
- Fragment 只能读取 State（通过 read_ports），不能写入
- Context 组装完成后的 `system_prompt` 是纯文本，流经 Brain

**它能表达什么**：

- Chat turn 输入：PromptCompiler 编译 fragment → system_prompt
- 异步触发输入：`TimerFired` 事件的 payload 是 Context
- 审批续接：`Brain.continue_after_tool_result` 重用同一条 Context 管线

**它不是什么**：

- **不是** Fragment 本身。Fragment 是 Context 的实现细节
- **不是** 对话历史。对话历史是 `messages` 投影（STATE）

---

## 2. 推导规则

以下规则回答一个问题：**如何用五原语表达现有的所有概念。**

### 2.1 通用推导法

```
概念 = EVENT(类型) + STATE(聚合表) + CAPABILITY(工具) + WORK(执行) + CONTEXT(输入)
         ↑                ↑                    ↑              ↑               ↑
      记录发生什么      保存当前状态        治理外部副作用    调度执行单元    提供触发条件
```

### 2.2 现有概念映射

| 现有概念 | 表达为 | 新概念？ |
|---|---|---|
| Goal | `Work(type=goal) + State(goals)` | Goal 语义特殊（树+进度），暂保留独立 |
| Task | `WorkItemCreated → work_items` | **已合并** (v0.5.0) |
| Action | `WorkItemCreated(work_type=action) → work_items` | **已合并** (v0.5.0) |
| Execution | `Work 的一个 lifecycle stage` | 执行记录，保留 |
| BackgroundTask | `Work(type=background)` | **否** |
| Memory | `State(memories) + recall Capability` + `Event(MemoryDerived/Updated/Deleted)` | 认知语义保留独立事件类型 |
| Approval | `Capability.gate` + `State(approvals)` | **否** |
| Notification | `Event(NotificationCreated)` + push `Context` 通道 | **否** |
| Conversation | `State(conversations) + Event(MessageAppended)` | **否** |
| Fragment | `Context 的生产函数（优先级 + 预算 + collect async）` | **否** |
| Principal | `Capability 的身份维度（system/user/agent）` | **否** |
| Policy / Grant | `Capability 的元数据（risk level + 授权关系）` | **否** |
| Trigger | `subscribe(Event) + invoke(Capability) + produce(Work)` | **已删除** (v0.6.0) → `@reaction` |
| Timer / Cron | `clock_source + subscribe + invoke + produce` | **否** |
| Kernel | 五个原语的**统一写入入口** + 边界守卫 | 必须存在 |
| Agent | Capability 授权的边界（Principal type=agent） | 概念保留，实现瘦身 |
| Schedule | clock source + `subscribe(Event) → invoke(Capability)` | **否** |

### 2.3 关键推导：Trigger 如何消失

当前 `TriggerEngine` 拥有 178 行命令式代码，独立于五原语。如果改为声明式 Reaction：

```python
@reaction(
    when=Event(type="InboxEmailRecorded", count_gte=50, window_days=1),
    then=Work(type="notification", template="收件箱积压..."),
)
def email_backlog():
    ...
```

那么：

- `trigger_engine.py` → **删除**
- `projectors_trigger.py` → **删除**
- `EVENT_TRIGGER_CREATED/DELETED` 常量 → **删除**
- `triggers` 表（当前是 APP_STORAGE，游离于事件溯源之外） → **删除**
- `RuntimeLoop._check_triggers` → **删除**

Reaction 不再是一个"概念"，而是 `subscribe + invoke + produce` 的组合实例。Runtime 负责在事件分发路径上评估 when 条件。

---

## 3. 三条判据

每新增一个概念、模块、目录、事件类型，必须通过以下三条检视。任何一条不通过，就不应该加。

### 3.1 Subsumption Test（吞并测试）

> **新增概念 X，能否用现有原语组合表达？**

```
能 → X 是组合，写成声明或实例。不加模块。
不能 → 问：是某个原语缺了什么？
        如果原语本身够用，是 X 的边界画错了。
        如果原语不够用，这才是原语本身的增长点。
```

**判例**：

- ✅ Fragment：能用 Context + State 表达 → 保留为组合，不作为原语
- ✅ Trigger：能用 subscribe + invoke + produce 表达 → 应消失为组合
- ❌ 早期 `CapabilityGateway`：后来发现只是 Capability 的决策 + Kernel 的调用 → 已合并

### 3.2 Concept Addition Cost（概念添加成本）

> **新增一个概念，就必须删除一个旧概念。**

强制零和。这是防 Framework Disease 的核心纪律。

**操作**：

1. 提出新增概念 X
2. 从现有概念清单中（见 §4）选一个标记为"应消失"
3. 在同一个 PR 中完成：加 X 的定义 + 删旧概念的代码

**如果找不到可删的**：
- 大概率 X 是现有概念的变体，不该成为独立概念
- 或者现有概念清单有遗漏（没有及时清理）
- 此时应该先清理再提新概念

### 3.3 One Year Test（一年测试）

> **这个概念一年后还会以独立身份存在吗？**

- 如果答案是不确定 → 默认不做
- 如果答案是"视情况而定" → 默认不做
- 只有当答案是 **"无论项目怎么演进，它一定在"** → 才做

**已有判例**：

| 概念 | 一年测试 | 结论 |
|---|---|---|
| `timer_engine.py` | 已迁入 RuntimeLoop，一年后大概率不存在 | 应删 |
| `background_worker.py` | 同上 | 应删 |
| `legacy_event_adapter.py` | 迁移完成后必然消失 | 应删 |
| `execution_shadow_compare.py` | 是验证工具，不应在生产路径 | 移到 tests/ |
| `_mixin_protocol.py` | Kernel 不应该是 mixin 集合 | 应删 |

---

## 4. 概念清单映射表

这是**事实清单**——不是设计文档，而是当前代码库中实际存在的概念 × 五原语的映射。每次 PR 应该更新这个表。

### 4.1 Kernel Space

| 模块 / 文件 | 行数 | 对应原语 | 一年测试 | 行动 |
|---|---|---|---|---|
| `kernel/kernel.py` | 759 | Event + Capability + Work | 必须存在 | refactor: 拆 emit/read/sovereignty |
| `kernel/kernel_query_state.py` | 543 | State | 必须存在但应瘦身 | 替换为类型化端口 |
| `kernel/kernel_sovereignty.py` | 511 | State（rebuild） | 必须存在 | 保留 |
| `kernel/kernel_governance.py` | 152 | Capability（approval） | 必须存在 | 保留，但有中文文案泄漏 |
| `kernel/projectors_*.py` | 10 个文件 | State | 必须存在 | 按聚合垂直拆分 |
| `kernel/constants.py` | 157 | Event（类型注册） | 必须存在但应只增事件、不增概念 | 锁定增长速率 |
| `kernel/event.py` | 77 | Event | 必须存在 | 保留 |
| `capability_governance.py` | 434 | Capability | 必须存在 | 拆 UI 标签逻辑 |

### 4.2 Orchestration

| 模块 | 行数 | 对应原语 | 一年测试 | 行动 |
|---|---|---|---|---|
| `runtime_loop.py` | 289 | Clock + Work | 存在但业务规则该移走 | 把 `_smart_notification_check` 移出 |
| `agent_scheduler.py` | 387 | Work | 必须存在 | 保留，去掉 Agent 依赖 |
| `runtime_container.py` | 294 | 容器 | 必须存在 | 统一游离单例 |
| `task_engine.py` | 132 | Work（CRUD） | **否** | **并入 Work Repository** |
| `background_worker.py` | 63 | Work（CRUD） | **已删除** (v0.4.0) | ✓ |
| `timer_engine.py` | 37 | Clock | **已删除** (v0.4.0) | ✓ |
| `cron_registry.py` | 69 | Clock | 保留（inlined ensure_schedules） | light |
| `trigger_engine.py` | 178 | Event + Capability + Work | **已删除** (v0.6.0) | ✓ → `@reaction` |
| `execution_events.py` | 134 | Work（事件辅助） | 必须存在 | 保留 |
| `execution_scope.py` | 33 | Work（ContextVar） | 必须存在 | 保留 |
| `work_item.py` | 152 | Work | 必须存在 | 保留 |
| `handler_registry.py` | 74 | Work（handler 路由） | 必须存在 | 保留 |
| `execution_shadow_compare.py` | 170 | 验证工具 | **否** | **移到 tests/**
| `reaction_registry.py` | new | Event + Capability + Work（声明式） | 必须存在 | ✓ 新概念
| `builtin_reactions.py` | new | 内置 Reaction 注册 | 必须存在 | ✓ 新概念 |

### 4.3 Context Pipeline

| 模块 | 行数 | 对应原语 | 一年测试 | 行动 |
|---|---|---|---|---|
| `governance/context_pipeline.py` | 182 | Context | 必须存在 | 简化层数 |
| `governance/context_policy.py` | 146 | Context | YAGNI Protocol | **删 Protocol，留 Default 实现** |
| `governance/fragment_selector.py` | 144 | Context | 可简化 | **3 层选择 → 1 个排序函数** |
| `governance/query_analyzer.py` | 98 | Context（意图标注） | 可选 | 可简化但**不删**（规则比 LLM 稳定） |
| `governance/execution_context.py` | 222 | Context | 必须存在 | 保留 |
| `governance/capability_context.py` | 285 | Capability（快照） | 合理 | 保留 |
| `assembler/context_assembler.py` | — | Context | 必须存在 | 保留 |

### 4.4 壳模块（已删除 ✓）

| 模块 | 文件 | 状态 |
|---|---|---|
| TimerEngine | `timer_engine.py` | **已删除** (v0.4.0) |
| BackgroundWorker | `background_worker.py` | **已删除** (v0.4.0) |
| Legacy Event Adapter | `legacy_event_adapter.py` | **已删除** (v0.4.0) → 替换为 `event_formatting.py` |
| Mixin Protocol | `kernel/_mixin_protocol.py` | **已删除** (v0.4.0) |
| Execution Shadow Compare | `execution_shadow_compare.py` | 保留（验证工具，后续移到 tests/） |

### 4.5 多 Agent 装饰（已瘦身 ✓）

| 模块 | 文件 | 状态 |
|---|---|---|
| AgentDefinition | `agent_definition.py` | **已删除** (v0.4.0) |
| AgentBootstrap | `agent_bootstrap.py` | **已简化** → `ensure_scheduler(kernel)` |
| AgentInstance | `agent_instance.py` | **已删除** (v0.4.0/v0.5.0) — `agent:primary` 字符串直接由 `agent_bootstrap.py` 内联 |
| AgentRegistry | `agent_registry.py` | **已瘦身** → stub with `cleanup_stale()` no-op |
| Principal | `principal.py` | **保留** — Capability 的身份维度 |

### 4.6 概念总数基线（2026-07-04）

| 指标 | 当前值 | 目标值 (1 年后) |
|---|---|---|
| `core/runtime/` 文件数 | 55 | ≤ 45 |
| `constants.py` 事件类型数 | 55 (+1 `MemoryIndexRepairFailed` for durable repair queue) | ≤ 50 |
| `query_state` selector 分支数 | 12 | ≤ 10 |
| Fragment 注册数 | 10 | ≤ 10 |
| Governed 投影表数 | 12 (-1 grant_events demoted to APP_STORAGE) | ≤ 11 |
| Projector 文件数 | 7 | ≤ 7 |
| 游离单例（不在 container 内） | 0 (v0.8.0: reset() drains handler/reaction/fragment/scheduler) | 0 |
| Dead code 文件数 | 0 | 0 |
| God Object 最大 LOC（Kernel/Brain/MCPHub） | 1908 | ≤ 1500 |

`check_concept_growth.py` 在 CI 中强制以上基线（[`backend/scripts/check_concept_growth.py`](../../backend/scripts/check_concept_growth.py)）。

---

## 5. 演进契约

这是 Runtime 的健康协议——不是 AI 生成的建议，而是**机器可验证的不变量**。

### 5.1 核心原则

> **一个健康的 Runtime，核心概念数应单调下降。**

证据：
- Linux 1.0 → 6.x：核心概念（fd/process/socket/signal）几乎不增，旧概念被淘汰（devfs/ipchains/a.out）
- BEAM VM：30 年核心概念稳定（process/message/link/monitor/supervisor）
- Tokio：从 mio 到 tokio，概念在收缩

反例（Framework Disease 的下场）：
- Spring 加概念 → 出 Spring Boot 来"简化" → 证明 Framework 失控
- Rails 每个 Active* 都是概念膨胀点

### 5.2 机器可验证的不变量（CI）

以下指标由 [`backend/scripts/check_concept_growth.py`](../../backend/scripts/check_concept_growth.py) 测量并在 CI 中强制（红线 = 当前基线值，详见 §4.6）。任何 PR 让指标**净增长** > 0 都会被阻断：

| 检查项 | 红线 | 测量方法 |
|---|---|---|
| `constants.py` 事件类型数 | 净增长 ≤ 0（删除需在同 PR） | `EVENT_[A-Z_]+\s*=\s*"` 计数 |
| `core/runtime/` 文件数 | 净增长 ≤ 0 | `find -name '*.py'` 递归计数 |
| `query_state` selector 分支数 | 净增长 ≤ 0（删除需在同 PR） | diff `if selector ==` 分支 |
| Fragment 注册数 | 净增长 ≤ 0（合并/删除需在同 PR） | diff `register.py` 的 `_ALL_FRAGMENT_CLASSES` |
| Governed 投影表数 | 净增长 ≤ 0（demote 需在同 PR） | diff `GOVERNED_TABLES` |
| God Object 最大 LOC（Kernel/Brain/MCPHub） | 净增长 ≤ 0 | 三个候选的 max LOC |
| Dead code 文件数 | 必须 = 0 | `_KNOWN_DEAD_FILES` 列表 |

**净增长判定**：当且仅当 PR 同时新增与删除等价概念时才允许突破红线。基线随 PR 的删除同步降低；新增而不删除会被 `check_concept_growth.py` 失败。

### 5.3 演进节奏

| 阶段 | 动作 | 目标 |
|---|---|---|
| v0.4.0 ✅ | 删壳 + 修读边界 + Agent 瘦身 | runtime 文件数 65 → 61 |
| v0.5.0 ✅ | Task + Action → WorkItem 统一 | governed 表 14 → 15（+1 换 -2 概念） |
| v0.6.0 ✅ | TriggerEngine → @reaction 声明 | projector 10 → 9, events 69 → 67 |
| v0.7.0 ✅ | grant_events demote + projectors 收尾 | governed 15 → 12（-3 actions/tasks/grant_events）|
| v0.8.0 ✅ | Memory Index 修复队列持久化 + reset() 全清 | 修复 silently 丢数据 + 测试隔离完整 |
| v1.0 | 合并 Goal 到 Work 原语 | governed 表 12 → 11 |

---

## 6. PR 对照清单

以下清单应放在 PR 模板中，每次提交前强制执行：

```markdown
## Runtime Algebra 审查

### 概念影响

- [ ] 本 PR 是否新增了**模块**（.py 文件）？
  - 若是：是否同时**删除**了一个旧模块？
- [ ] 本 PR 是否新增了**事件类型**（constants.py 的 EVENT_*）？
  - 若是：被替换的是哪个旧事件类型？
- [ ] 本 PR 是否新增了**Fragment**？
  - 若是：被合并/删除的是哪个旧 Fragment？
- [ ] 本 PR 是否新增了**投影表**？
  - 若是：是否可以用现有表表达？

### 一年测试

- [ ] 新增的每一个概念：一年后还会以独立身份存在吗？
  - 不确定 → 标注 `// EXPERIMENTAL: review by 20xx-xx`
  - 一定不存在 → 标注 `// DEPRECATED: migrate to X by vx.x`

### 吞并测试

- [ ] 新增概念能否用现有五原语（Event/State/Capability/Work/Context）组合表达？
  - 能 → 写为声明/实例，不要加新模块
  - 不能 → 在 PR 描述中解释为什么五原语不够

### 审查人检查

- [ ] `core/runtime/` 文件数：__（变更前） → __（变更后）
- [ ] `constants.py` 事件类型数：__（变更前） → __（变更后）
- [ ] Fragment 注册数：__（变更前） → __（变更后）
```

---

## 7. 边界之外

以下不属于 Runtime Algebra 的范畴，不影响原语数量：

- **Prompt 模板** — 属于 CONTEXT 的配置，不是新原语
- **前端组件 / 页面** — User Space，不在 Kernel Space 内
- **桌面包装** — Electron 层，不是 Runtime
- **Alembic 迁移** — schema 演化工具，不增加概念
- **CI / 验证脚本** — 基础设施，不增加概念
- **配置（.env / mcp_config.json）** — 声明式配置，不是代码概念

---

## 8. 修订历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-03 | v0.1 | 初始版本：定义五原语 + 三条判据 + 概念清单基线 |
