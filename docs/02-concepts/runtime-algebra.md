# Runtime Algebra

本文档定义 Personal AI Runtime 的**最小公理系统**。它不是描述"现在有什么"，而是定义"一切应该能推导回什么"。

它的目的是：

- 成为所有增加/删除概念的判据
- 防止 Framework Disease（通过不断增加抽象来扩展）
- 确保 Runtime 的核心概念数单调下降

> **Runtime 通过组合原语来扩展；Framework 通过增加概念来扩展。本文档存在的唯一目的，是确保这个项目走前者的路。**

---

## 1. 六个原语

任何不在以下六者之中的概念，要么是组合，要么是多余的。

```
EVENT      — 不可变事实（已发生、不可撤销）
STATE      — Event 的物化视图（可以从 Event 重建）
CAPABILITY — 受治理的工具调用（身份 + 授权 + 审计）
WORK       — 待执行的计算单元（有生命周期、可重试、可归属）
CONTEXT    — 触发 WORK 的输入（消息 + 环境快照）
TRANSPORT  — 瞬时推送通道（不入 event_log、容许丢失）
```

### 1.1 Event

**定义**：描述已发生事实的不可变记录。唯一写入入口是 `Kernel.emit_event()`。

**不变量**：

- `event_log` 是 append-only（SQLite 触发器强制；rebuild/restore 为特权路径，受锁保护）
- Event 一旦写入，payload 不可篡改
- 全部 STATE 都可以从 Event 重放重建

**它能表达什么**：

- 用户动作：`WorkItemCreated`、`MemoryUpdated`、`MessageAppended`
- 系统动作：`TimerFired`、`ExecutionStarted`、`CapabilityInvoked`
- 业务状态转换：所有 `XxxCreated/Updated/Deleted` 系列

**它不是什么**：

- **不是**流式内容（token delta 不入 event_log；见 TRANSPORT）
- **不是**请求的即时响应（请求和完成是两个独立 Event）
- **不是**RPC（`submit_command` 是 Event 上的同步包装，不是新原语）

### 1.2 State

**定义**：Event 的物化视图。State 存在于 governed 投影表（`work_items`、`memories`、`conversations` 等），由 projector 从 event_log 同步投影。

**不变量**：

- State 必须可从 Event 完整重建（`kernel.rebuild_all()` 验证）
- 所有 governed 投影表写入通过 Kernel 的 `projectors.apply(event, conn)`
- 读操作通过 `kernel.query_state(selector)` 或类型化 Read Port

**它能表达什么**：

- 聚合的当前视图：`work_items` 表（含 `work_type='goal'` 行）、`memories` 表、`notifications` 表
- 向量索引：ChromaDB 是 memories 的派生索引（非独立 State）
- 配置文件快照：`app_settings` 是 local config 的物化

**它不是什么**：

- **不是**缓存（APP_STORAGE 表可以直访，不需要事件溯源）
- **不是**中间计算结果（那些属于 WORK 的执行过程，不进事件日志）

### 1.3 Capability

**定义**：以受治理方式执行外部效果的能力。所有工具调用（内置 + MCP）的唯一入口是 `Kernel.invoke_capability()`。

**不变量**：

- 3-gate 授权：forbidden → pre-approved → risk assessment
- 所有工具调用产生可审计事件：`CapabilityInvoked/Failed/Denied/Deferred`
- 外部摄入类工具污染当前 `correlation_id`（taint 追踪）

**它能表达什么**：

- 读取：`web_search`、`check_inbox`、`list_calendar_events`（auto_allow）
- 写入：`write_file`、`send_email`、`shell_exec`（needs_user）
- 组合：`fetch_url`（摄入） → `write_file`（污染后强制 high risk）
- Agent 授权：由 `policy_events` 投影控制各 Capability 的风险等级

### 1.4 Work

**定义**：需要被执行的计算单元。有两类 subtype，不要混淆为两套模型：

1. **领域 Work** — `work_items` 投影（goal / task / action）
2. **调度 Work（ScheduledExecution）** — `handler_executions`（一次 handler 调用）

详见 [execution-model.md](execution-model.md)。类名 `WorkItem`（执行）已收敛为 `ScheduledExecution`，避免与领域表同名。

领域 Work 与调度 Work 同属 WORK 原语的两个 subtype：前者是用户可见的业务对象，后者是运行时执行记录。二者不可合并到同一张表（会把 progress/importance 与 retry_count/policy_json 混杂），也不可拆成两个原语（都会引入平行生命周期叙事）。

**统一要求**：后台异步任务应表达为 WORK（领域 subtype），而不是平行的第二套任务表。`background_tasks` 已是 GOVERNED 投影（`BackgroundTask*` → projector），属 WORK 的领域 subtype 物化；与 `work_items` 分表是待收敛的存储缺口（INV-W5），不是第二套原语，也不是 APP_STORAGE。

**不变量**：

- Lane A 执行必须绑定 `execution_id`（= ScheduledExecution.id）
- 中断恢复：从 `handler_executions` 投影重建
- Lane A 状态转换通过 Event（`ExecutionRequested → Started → Completed/Failed → Retried`）
- Reaction 不是原语，是 `subscribe + emit/invoke` 的组合（Lane C）

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

### 1.6 Transport

**定义**：把事实或过程信号瞬时推送到外部消费者（SSE、WebSocket、进程内广播），**不**写入 `event_log`。

**为什么必须是原语**：

- Event 承诺持久化与可重建；Transport 承诺实时性与可丢失
- 聊天 `text_delta` 等流式内容若写入 Event，会污染真相层并拖垮重建
- 源码显式区分二者：`EVENT_CHAT_TEXT_DELTA` 故意不 emit 到 `event_log`，经 [`notification_bridge.py`](../../backend/app/core/runtime/notification_bridge.py) 推送

**不变量**：

- Transport 失败不得回滚已提交的 governed 写入
- Transport 不是 State 的投影；丢失可接受，客户端可重新拉取 State
- 进入 `event_log` 的仍是完成态事实（如 `ChatCompleted`），不是流式增量

**它能表达什么**：

- SSE 聊天增量、审批/记忆/目标变更的前端失效信号
- WebSocket 心跳与广播

**它不是什么**：

- **不是** Event 的副作用别名（二者生命周期与失败语义不同）
- **不是** Notification 业务语义（通知内容是 Event + State；投递通道是 Transport）

---

## 2. 推导规则

以下规则回答一个问题：**如何用六原语表达现有的所有概念。**

### 2.1 通用推导法

```
概念 = EVENT + STATE + CAPABILITY + WORK + CONTEXT + TRANSPORT
         ↑       ↑         ↑          ↑        ↑          ↑
      记录发生  当前视图   治理副作用   执行单元   触发输入   瞬时推送
```

### 2.2 现有概念映射

| 现有概念 | 表达为 | 备注 |
|---|---|---|
| Goal | `Work(type=goal) + State(work_items)` | Goal 语义特殊（树+进度），独立 work_type |
| Task | `WorkItemCreated(work_type=task) → work_items` | 统一到领域 Work |
| Action | `WorkItemCreated(work_type=action) → work_items` | 统一到领域 Work |
| ScheduledExecution | `Work` 的调度 subtype | `handler_executions` |
| BackgroundTask | `Work` 的领域 subtype | GOVERNED `background_tasks` 投影；与 `work_items` 分表待收敛（INV-W5） |
| Memory | `State(memories) + recall Capability` + `Event(Memory*)` | 认知语义保留独立事件类型 |
| Approval | `Capability.gate` + `State(approvals)` | — |
| Notification | `Event(NotificationCreated)` + Transport 投递 | — |
| Conversation | `State(conversations) + Event(MessageAppended)` | — |
| Fragment | `Context` 的生产函数 | — |
| Principal | `Capability` 的身份维度 | — |
| Policy | `Capability` 的元数据 | — |
| Reaction | `subscribe(Event) + invoke(Capability) + produce(Work)` | **非原语**；Lane C |
| Timer / Cron | `clock_source + subscribe + invoke + produce` | — |
| Kernel | Event / State / Capability 的**统一写入入口** + 边界守卫 | 必须存在 |
| text_delta / SSE | Transport | 不进 event_log |

### 2.3 关键推导：Reaction 模型

Runtime 的周期性/事件触发动作通过声明式 Reaction 表达：

```python
@reaction(
    when=Event(type="InboxEmailRecorded", count_gte=50, window_days=1),
    then=Work(type="notification", template="收件箱积压..."),
)
def email_backlog():
    ...
```

Reaction 不是独立"概念"，而是 `subscribe + invoke + produce` 的组合实例。Runtime 负责在事件分发路径上评估 when 条件。

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
- ✅ Notification 投递：Event + Transport → 不新增投递原语
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

### 3.3 Durability Test（持久性测试）

> **这个概念是否无论产品怎么演进，都必须以独立身份存在？**

- 如果答案是不确定 → 默认不做
- 如果答案是"视情况而定" → 默认不做
- 只有当答案是 **"它是原语或原语的必要机制，去掉系统无法表达某类问题"** → 才做

---

## 4. 概念清单映射表

这是**事实清单**——当前代码库中实际存在的概念 × 六原语的映射。结构变化时应更新本表。

### 4.1 Kernel Space

| 模块 / 文件 | 对应原语 | 角色 |
|---|---|---|
| `kernel/kernel.py` | Event + Capability + Work | 统一写入入口 |
| `kernel/kernel_query_state.py` | State | 查询面 |
| `kernel/kernel_sovereignty.py` / `sovereignty_ops.py` | State | rebuild / export / import |
| `kernel/governance_ops.py` | Capability | `invoke_capability` |
| `kernel/projectors_*.py` | State | 按聚合投影 |
| `kernel/constants.py` | Event | 事件类型注册 |
| `kernel/event.py` | Event | Event 值类型 |
| `capability_governance.py` | Capability | 3-gate 决策 |

### 4.2 Orchestration

| 模块 | 对应原语 | 角色 |
|---|---|---|
| `runtime_loop.py` | Work + clock | Lane C 维护循环 |
| `agent_scheduler.py` | Work | Lane A 调度 |
| `runtime_container.py` | （容器） | 依赖装配 |
| `task_engine.py` | Work | 领域 Work CRUD（偏 Product 编排） |
| `cron_registry.py` | clock + Work | 定时触发 |
| `execution_events.py` / `execution.py` | Work | 调度 subtype 辅助 |
| `scheduled_execution.py` / `work_item.py` | Work | 调度 / 领域常量 |
| `handler_registry.py` | Work | handler 路由 |
| `reaction_registry.py` | Event + Capability + Work | 声明式组合 |
| `builtin_reactions.py` | Reaction 实例 | 产品策略反应（应逐步产品化） |
| `notification_bridge.py` / `notification_channel.py` | Transport | SSE / WS / 广播 |

### 4.3 Context Pipeline

| 模块 | 对应原语 | 角色 |
|---|---|---|
| `governance/context_pipeline.py` | Context | 编译管线 |
| `governance/context_policy.py` | Context | 编译策略 |
| `governance/fragment_selector.py` | Context | Fragment 选择 |
| `governance/query_analyzer.py` | Context | 意图标注 |
| `assembler/context_assembler.py` | Context | 文本组装 |

### 4.4 概念压缩红线（CI 契约）

以下数字是 **CI 红线（上限）**，与 [`check_concept_growth.py`](../../backend/scripts/check_concept_growth.py) 的 `BASELINE` 同步。它们不是架构叙事，也不预测未来规模；任何净增长必须在同 PR 内零和抵消，或显式更新红线并说明替换了哪个旧概念。

| 指标 | 红线（上限） |
|---|---|
| `core/runtime/` 文件数 | 66 |
| `constants.py` 事件类型数 | 50 |
| `query_state` selector 分支数 | 18 |
| Fragment 注册数 | 10 |
| Governed 投影表数 | 16 |
| Projector 文件数 | 6 |
| God Object 最大 LOC（Kernel/Brain/MCPHub） | 648 |

`check_concept_growth.py` 在 CI 中强制以上红线。原则说明见 [architecture-principles.md](architecture-principles.md)。

---

## 5. 概念压缩契约

这是 Runtime 的健康协议——**机器可验证的不变量**。

### 5.1 核心原则

> **一个健康的 Runtime，核心概念数应单调下降。**

Runtime 通过组合原语扩展；通过淘汰旧概念压缩。新增概念而不删除旧概念，是 Framework Disease 的早期信号。

### 5.2 机器可验证的不变量（CI）

以下指标由 [`check_concept_growth.py`](../../backend/scripts/check_concept_growth.py) 测量并在 CI 中强制。任何 PR 让指标**净增长** > 0 都会被阻断（红线见 §4.4）：

| 检查项 | 规则 | 测量方法 |
|---|---|---|
| 事件类型数 | 净增长 ≤ 0 | `EVENT_* = "..."` 计数 |
| `core/runtime/` 文件数 | 净增长 ≤ 0 | 递归 `.py` 计数 |
| `query_state` selector | 净增长 ≤ 0 | `if selector ==` 分支 |
| Fragment 注册数 | 净增长 ≤ 0 | `_ALL_FRAGMENT_CLASSES` |
| Governed 投影表数 | 净增长 ≤ 0 | `GOVERNED_SCHEMA` 键 |
| God Object 最大 LOC | 净增长 ≤ 0 | Kernel / Brain / MCPHub |

**净增长判定**：当且仅当 PR 同时新增与删除等价概念时才允许突破；红线随删除同步降低。抬红线必须在 PR 中说明替换掉的旧概念，并同步更新 §4.4 与脚本 `BASELINE`。**禁止静默抬红线。**

### 5.3 功能闸门

1. **吞并测试先行**：新需求先尝试用六原语组合表达。能用现有事件类型 + 投影表 + fragment + capability + transport 表达 → 写为声明/实例，不加新模块。
2. **零和强制**：若必须新增概念，同 PR 必须删除一个等价旧概念。
3. **抬红线需说明**：见 §5.2。

**反模式**：

- 为了「架构更干净」而压缩概念，但该概念当前并无日用阻碍（优先用 dogfood 证据，见 [development.md](../05-engineering/development.md)）。
- 新增事件类型而不删旧类型。
- 用平行任务表 / 平行调度叙事绕过 WORK 原语。

---

## 6. PR 对照清单

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

### 持久性测试

- [ ] 新增的每一个概念：去掉它，系统是否无法表达某类问题？
  - 不确定 → 不做，或标为实验性实现细节

### 吞并测试

- [ ] 新增概念能否用现有六原语组合表达？
  - 能 → 写为声明/实例，不要加新模块
  - 不能 → 在 PR 描述中解释为什么六原语不够
```

---

## 7. 边界之外

以下不属于 Runtime Algebra 的范畴，不影响原语数量：

- **Prompt 模板** — 属于 CONTEXT 的配置，不是新原语
- **前端组件 / 页面** — User Space，不在 Kernel Space 内
- **桌面包装** — Electron 层，不是 Runtime
- **Alembic schema** — 初始化工具，不增加概念
- **CI / 验证脚本** — 基础设施，不增加概念
- **配置（.env / mcp_config.json）** — 声明式配置，不是代码概念
- **具体 Product 能力实现**（邮件/日历/知识库策略）— 通过 Capability / State 挂接，本身不是原语
