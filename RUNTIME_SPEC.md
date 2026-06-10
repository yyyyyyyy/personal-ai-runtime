# Personal AI Runtime · 架构规格（RUNTIME_SPEC）

> 这份文档不是 API 设计，也不是实现计划。它定义的是这个项目从 **Personal AI App** 扭转成 **Personal AI Runtime** 的两块地基：
> **① Runtime Primitive（对象模型）** 和 **② Kernel Boundary（边界）**，最后才是 **③ Kernel ABI**。
> 顺序不能反——先有严格定义的对象，API 才有意义；否则半年后会陷入「先写 API → 改 API → 兼容 API → 背历史包袱」。
>
> 状态：**v1.0 — FROZEN（对象模型已冻结）** ｜ 适配代码基线：backend **v0.9.0**
>
> 冻结声明：7 个 Primitive、1 条 Boundary、1 组 ABI 已收敛完成，**不再新增 Primitive、不再加 Layer、不再扩 Runtime 概念**。
> v1.0 相对 v0.1 仅吸收三处外科级微调：①`subject` → `aggregate_type + aggregate_id` ②`caused_by` 增补 `correlation_id` ③ABI 新增 `subscribe_events`。
> **v0.9.0：** W1–W4 实现已完成；`verify_rebuild.py` 验证 Event → State 重建。规格变更需 RFC（见 Governance Charter）。

---

## Governance Charter

Personal AI Runtime exists to govern personal agent behavior.

It does not exist to provide features.

Features are Apps. Governance is Runtime.

A change requires RFC only if it changes the MUST semantics of a Runtime Primitive.

**Maintainer lint:** Does this change require modifying a Primitive's MUST definition? If no → App / Capability / Projection / Policy. If yes → RFC.

**Facts vs interpretation:** Runtime provides facts (`query_state`, `read_events`). Apps provide interpretation (briefs, reviews, dashboards, scores).

Enforcement: `backend/scripts/check_boundary.py` (CI) — governed projection reads/writes outside `kernel/` fail the build.

---

## W5 — Runtime Closure Validation (v1)

W5 is not a debt sprint. It validates **Runtime Closure**: the Runtime is closed for v1 — Apps need not bypass it, and it need not grow new read/write ABI for validated product scenarios.

| Closure path | Guard | Status |
|--------------|-------|--------|
| Write: Event → State | `verify_rebuild.py` | ✓ |
| Read: State → App | Read Surface v1 (`query_state`, `read_events`) | ✓ PASS |
| Boundary: App ↛ governed DB | `check_boundary.py` | ✓ Debt 0 |
| ABI surface | No expansion during validation | ✓ 0 new ABI |

**Sufficiency** = current apps work. **Closure** = current apps work *and* new apps should default to the same ABI without `query_*()` proliferation.

**Scope** (validated alongside Closure): Runtime exposes **facts** (projections, events); Apps own **interpretation** (briefs, stats, insights, summaries). Product semantics must not migrate into Kernel as `query_review()` / `query_dashboard()` / Knowledge primitives.

| Layer | Provides | Must not provide |
|-------|----------|------------------|
| Runtime | Facts via `query_state`, `read_events`, capabilities | Product semantics, aggregation meaning, "what to remind today" |
| App | Interpretation, UI, stats, trends, narratives | Direct governed DB access |

**W6+ scope test:** Can Knowledge / Mail / proactive layer ship without `query_knowledge()`, `query_chunks()`, or a Knowledge Primitive? If yes — Closure and Scope hold. If no — Scope is drifting even if Closure holds.

Validated in-repo (2026-06-10):

| App | Path | Read ABI used | New ABI added |
|-----|------|---------------|---------------|
| Morning Brief | `product/morning_brief.py` | `query_state("goals", ...)` | None |
| Review | `core/review_engine.py` | `query_state` + `read_events` + `to_legacy_dict` | None |
| Dashboard | `core/telemetry/telemetry.py` | `query_state("memories" \| "tasks", ...)` + App aggregation | None |
| Deadline Alert | `core/scheduler.py` | `query_state("goals", deadline_within_days=...)` | None |

**Conclusion:** W5 validated **Runtime Closure** and **Runtime Scope** for v1.

- **Closure:** product apps implementable without expanding Runtime ABI (`query_state` + `read_events` closed for validated apps).
- **Scope:** product semantics stay in Apps; Runtime exposes facts, not interpretations.

Runtime Read Surface v1 = `query_state()` + `read_events()`. Aggregation, sorting, narratives, and metrics belong in Apps.

**ABI guard question:** Before adding `query_*_stats()` or similar — why did Brief / Review / Dashboard / Deadline Alert not require it?

**W6+ question:** Is Closure *stable*? (Knowledge, Mail, proactive layer, coding agent — do they still fit without new ABI?)

**Boundary debt:** 0 (`make boundary-strict` passes).

### W5.1 — Extended Apps (post-validation, v0.9.0)

These ship **without** new Kernel read ABI (`query_mail()` etc.). Mail and cognition stay in App / Cognitive layers.

| App / Layer | Path | Mechanism | New Kernel ABI |
|-------------|------|-----------|----------------|
| **Inbox** | `product/inbox.py`, `api/inbox.py` | `invoke_capability("check_inbox")` + App table `inbox_emails` | None |
| **Pattern** | `runtime/pattern/aggregators.py` | Subscribe `ActivityNormalized` → emit `PatternDetected` | None (writes via `emit_event`) |
| **Belief** | `belief/belief_engine.py` | Read `query_state("patterns"…)` → emit `BeliefFormed` | None (read-only + emit) |

**Mail semantics:** Chat tool `check_inbox` defaults to all recent mail (`unread_only=false`). Background inbox poll uses `unread_only=true` (new mail only).

**MCP tools:** 23 registered (CI-enforced), including `check_inbox`, `read_inbox_email`, `open_web_page`, `search_and_extract`.

---

## 0. 第一性原理：Runtime 的本质是「边界」，不是「状态」

很多 AI 项目有了 `Memory + Agent + Tools + SQLite` 就自称 Runtime。**这是错的。**

Runtime 最核心的特征不是「有状态」，而是「**有边界**」：

```text
Linux:   App → Syscall → Kernel → Hardware
              （App 永远不能直接改内存/磁盘/网络）

本项目:  Agent → Kernel ABI → Kernel → Storage / World
              （Agent 永远不能直接读写 SQLite / ChromaDB / 文件系统）
```

### 历史基线（Pre-W1）：没有边界 — **已在 W1–W4 解决**

> **v0.9.0 现状：** User Space 经 `kernel.emit_event` / `query_state` / `invoke_capability` 访问治理域；`check_boundary.py` CI 门禁，Boundary Debt = 0。以下描述的是 **W1 之前** 的债务，保留作动机说明。

核验 W1 前代码（`backend/app/store/database.py`）可以确认，当时的调用链是：

```text
Planner / Brain / 各 API
        ↓  直接 import store
   db.execute("UPDATE ...") / db.execute("DELETE ...")
        ↓
     SQLite / ChromaDB
```

也就是说：

```text
当前  Agent = Root 权限
```

任何 Agent / 模块都能直接 `UPDATE` / `DELETE` 任意表（代码里 `delete_conversation` 等直接删表即是例证）。
**这不是 Runtime，这只是「Agent 直连数据库」。**（W1–W4 已按此铁律收敛。）

> 本规格要确立的唯一铁律：
> **Agent 处于 User Space，只能调用 Kernel ABI；只有 Kernel 处于 Kernel Space，独占对存储与外部世界的访问权。**

---

## 1. Runtime Primitive（对象模型 · 先定义对象，不定义 API）

Runtime 由 **7 个原语对象**构成。先把每个对象「是什么」定义到不可争辩，再谈接口。

下表是总览，随后逐个给出严格定义、可变性、与现有代码的映射、以及需要改造的缺口：

| Primitive | 一句话定义 | 可变性 | 是否可重建 |
|-----------|-----------|--------|-----------|
| **Event** | 发生过的事情（系统真相） | 只追加 / 不可变 / 有序 | ❌ 不可重建（丢了就没了） |
| **State** | 当前事实快照 | 可变 / 可覆盖 / 只留最新值 | ✅ 可由 Event 重建 |
| **Memory** | 从 Event 派生的、可衰减的信念 | 追加 + 置信度更新 | ✅ 可由 Event 重建 |
| **Capability** | 与外部世界交互的接口 | 注册表（声明式） | — |
| **Approval** | 能力调用的治理裁决 | 不可变（裁决一旦做出即固化） | — |
| **Task** | Runtime 的调度单位 | 状态机 | ✅ 可由 Event 重建 |
| **Agent** | 临时执行单元 | ephemeral（用完即销毁） | — 不持久 |

### 1.1 Event（事件）—— 系统真相，最优先

```text
定义：发生过的、不可否认的事实
属性：只追加（append-only）、不可变（immutable）、全局有序、可重放（replayable）
例子：MessageReceived / GoalCreated / TaskCompleted / FileModified / CapabilityInvoked / AgentSpawned
```

**为什么 Event 必须最优先（这是最容易被忽略的一点）：**

```text
State      = 当前结果   → 可以从 Event 重建
Memory     = 历史摘要   → 可以从 Event 重建
World Model = 趋势推演   → 可以从 Event 重建
———————————————————————————————————
Event Log  = 真相       → 丢了就永久丢失，无法重建
```

所以一切的起点是 **不可变、有序的 Event Log**。它是 Runtime 的「黑匣子」。

**Pre-W1 基线 vs 目标（W4 后已实现 `event_log` + legacy adapter）：**

```59:67:backend/app/store/database.py
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    summary TEXT NOT NULL,
    goal_id TEXT,
    payload TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (goal_id) REFERENCES goals(id)
);
```

Pre-W1 时 `events` 表只是一张**业务表**。**v0.9.0：** 治理域真相在 append-only `event_log`（`seq`、不可变）；旧 `events` 表经 `legacy_event_adapter` 供 Timeline 等读取。

要成为真正的 Event Log，规格要求（已实现）：

- **单调递增序号 `seq`**（全局有序的唯一真相来源，时间戳不够，会撞）
- **追加唯一性**：只允许 INSERT，**永不 UPDATE / DELETE**（数据库层面用触发器/约束兜底）
- **结构化 schema（v1.0 冻结）**：

```text
Event {
    seq              # 全局单调递增序号（唯一真相顺序，非时间戳）
    id               # 事件唯一 id
    type             # GoalCreated / TaskCompleted / FileWritten ...

    aggregate_type   # 该事件属于哪类聚合：goal / task / user / conversation ...
    aggregate_id     # 具体聚合实例：goal-123

    actor            # 谁触发的：user / agent:xxx / kernel / scheduler

    payload          # 事件数据

    caused_by        # 因果链：直接由哪个事件导致（上一跳）
    correlation_id   # 调度链/追踪链：同一意图产生的所有事件共享一个 id（trace_id）

    ts               # 时间戳（仅供展示/分析，排序以 seq 为准）
}
```

  - **`aggregate_type + aggregate_id` 取代旧的 `subject`**：让 `GoalCreated / GoalUpdated / GoalCompleted` 天然按聚合归并，`rebuild(goal-123)` 只需 `WHERE aggregate_type='goal' AND aggregate_id='goal-123'` 顺序重放。
  - **`caused_by` 与 `correlation_id` 是两种不同的关系**，缺一不可：
    - `caused_by` = **因果链（上一跳）**：`GoalCreated → TaskCreated → AgentSpawned → FileWritten`，每个只记直接前驱。
    - `correlation_id` = **追踪链（整条）**：一句「帮我写周报」可能产生 30 个事件，它们共享同一个 `correlation_id`，于是 `show trace report_abc` 能一次拉出整条链路。这是调试动态 Agent Runtime 的关键能力，类似 HTTP 的 `trace_id`。
- **解耦**：事件不再只能挂在 `goal_id` 上（由 `aggregate_type/aggregate_id` 通用化）。

### 1.2 State（状态）—— 当前事实快照

```text
定义：用户/系统当前的事实状态
属性：可变、可覆盖、只保留最新值（point-in-time snapshot）
例子：当前公司 / 当前城市 / 当前正在进行的项目 / 某目标的当前进度
本质：它是 Event 流的「物化视图（materialized view）」
```

**关键架构承诺**：State 不是被「直接写」的，而是 Event 的投影。
`GoalCreated` 事件 → 投影出 `goals` 里的一行；`CityChanged` 事件 → 覆盖 `state.city`。

> 现状：`goals` / `user_profile` 等是被各处直接 UPDATE 的。目标态：它们成为 Event 的 projection，可被 `replay(events)` 完整重建。

### 1.3 Memory（记忆）—— 派生的、可衰减的信念

> **这里我要锐化你给的定义。** 你把 Memory 定义为「历史事实 / 不可修改 / 只能追加」——但这样 Memory 会和 Event **塌缩成同一个东西**。必须把两者切开：

```text
Event  = 原始真相      「2026-06-01 用户在对话里说了：我最近在学 Rust」（系统级、客观、不可变）
Memory = 派生的信念    「用户偏好 Rust」 confidence=0.8（语义级、主观、可衰减、可被推翻）
```

```text
定义：从 Event 中抽取/归纳出来的、关于用户与世界的语义信念
属性：
  - 记录本身追加写（保留来源可追溯）
  - 但携带 confidence（置信度），会随时间衰减、被新证据更新或推翻
  - 可向量检索（语义召回）
  - 整个 Memory 集合可由 Event Log 重新抽取重建
例子：用户偏好 Rust(0.8) / 用户重视健康(0.6) / 用户讨厌开会(0.5)
```

**Pre-W1 基线 vs 目标（v0.9.0 已实现 Event 投影 + confidence）：**

```69:76:backend/app/store/database.py
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    embedding_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Pre-W1 时 `memories` 无 `confidence` / decay。**v0.9.0：** `MemoryDerived` / `MemoryDecayed` 事件 + 投影器；Chroma 为派生索引；`memory_extractor` 对话后异步抽取。

> **Event / State / Memory 三者构成经典三层，且彼此正交、不重叠——这是本规格最重要的收敛成果：**
>
> ```text
> Event   = 发生过什么   →  Truth        （真相，不可变）
> State   = 现在是什么   →  Projection   （投影，可重建）
> Memory  = 系统相信什么 →  Belief       （信念，可重建、可衰减）
> ```
>
> **关键推论：未来不需要再为 `World Model` / `User Model` / `Preference Model` 发明新对象——它们全部是 Memory 的不同视图，挂在 Memory 之下即可。** 这正是「不再扩 Primitive」的底气所在。

### 1.4 Capability（能力）—— 与世界交互的接口

```text
定义：Runtime 对外部世界的一切交互接口
属性：声明式注册表，每个能力声明其风险等级与所需授权
例子：filesystem / browser / email / calendar / shell / git / telegram
```

> **v0.9.0：** `MCPHub` 注册 **23** 个工具；User Space 经 `kernel.invoke_capability` 调用（W3）；高风险工具带 `needs_confirmation`。

### 1.5 Approval（审批）—— 能力调用的治理层

```text
定义：对「某次能力调用是否被允许」的治理裁决
属性：裁决一旦做出即不可变（落审计）；裁决前可挂起等待
裁决来源：分级授权策略（自动放行 / 需用户确认 / 永久禁止）
```

> **v0.9.0：** Brain 经 `invoke_capability` 挂起待审批；前端 `resolve_approval` 闭环；裁决走 `kernel.grant_approval` / `deny_approval`（W3）。

### 1.6 Task（任务）—— Runtime 的调度单位

```text
定义：Runtime 调度的最小单位，承载「要完成的一件事」
属性：状态机（pending → running → done/failed/suspended），可被 Event 重建
```

> 现状：`TaskEngine` + `StateManager` 存在。目标态：Task 的每次状态迁移都 emit 事件。

### 1.7 Agent（智能体）—— 临时执行单元

```text
定义：为完成某个 Task 而被 Kernel 临时拉起的执行单元
属性：ephemeral（短命）—— 不是长期存在的对象，用完即销毁
关键：Agent 是「上下文窗口」，不是「进程常驻」
```

```text
✅ 正确模型：Task → Kernel spawn 临时 Agent(s) → 完成 → 销毁
❌ 错误模型：Planner/Critic/Researcher 7×24 永久常驻
```

> 这呼应了产品评审里的判断：未来是**动态 Agent 生态**，不是固定 Agent 团队。
> 正因为 Agent 短命且可替换（今天 Brain、明天 Claude Code / Cursor Agent / OpenAI Agent），所以**稳定的必须是它们脚下的 Kernel**。

> **[Post-v1 备忘 · 不影响 v1 冻结]** 现在 `Agent` 仍偏 Agent-centric（`Task → spawn Agent → destroy`）。未来当 Claude Code / Cursor Agent / OpenAI Agent SDK / Browser Agent 都只是「执行后端」时，更干净的模型可能是 `Task → Execution → Agent`，即把 **`Execution` 提升为 Primitive，`Agent` 降级为 Execution Strategy**。
> **这是一个观察，不是 v1 的改动**——记录在案，待动态 Agent 生态真正落地、有真实多后端需求时再评估。在那之前不动。

---

## 2. Kernel Boundary（边界 · 什么能直接访问，什么必须走 Kernel）

这是把上面 7 个对象「焊成 Runtime」的那道线。

### 2.1 两个空间

| 空间 | 谁在这里 | 权限 |
|------|---------|------|
| **Kernel Space** | Kernel 本体：Event Log、State/Memory 投影器、Capability 注册表、Approval 策略引擎、Scheduler | **独占**访问存储（SQLite/ChromaDB）与外部世界（文件/网络/邮件…） |
| **User Space** | 一切 Agent、Workflow、Planner、Critic、未来接入的 Claude Code / Cursor Agent、甚至 UI | **只能调用 Kernel ABI**，不持有任何存储句柄 |

### 2.2 边界规则（铁律）

| 行为 | 允许？ |
|------|--------|
| User Space 直接 `import store` / 执行 SQL | ❌ 禁止 |
| User Space 直接读写文件 / 发网络请求 | ❌ 禁止（必须经 `invoke_capability`） |
| User Space 直接改 State | ❌ 禁止（State 是 Event 投影，不可直接写） |
| User Space 调用 Kernel ABI | ✅ 唯一通道 |
| Kernel 访问存储 / 外部世界 | ✅ 独占 |
| 任何**改变系统的** ABI 调用 | ✅ **必须 emit 对应 Event** |

> 最后一条是把 Event 变成「真相」的机制保证：**凡是改变了系统的操作，必然在 Event Log 留痕。** State 与 Memory 因此永远可由 Event 重建。

---

## 3. Kernel ABI（系统调用 · 最后才定义）

设计为 **`kernel.verb()` 形态**，而非 `runtime.memory.add()` 这种 Service API。
原因：未来 Agent 不重要、Workflow 不重要、甚至 UI 都不重要——**唯一稳定的是 Kernel**。就像 Chrome / VSCode / 微信 / 游戏最终都走 Linux Syscall，而不是各自访问磁盘。

### 3.1 核心 ABI（最小完备集）

```text
# —— 真相层（最先实现）——
kernel.emit_event(type, aggregate_type, aggregate_id, payload, actor, caused_by, correlation_id) -> EventRef
kernel.read_events(filter, since_seq) -> [Event]        # 重放 / 投影 / 审计的基础（拉模式）
kernel.subscribe_events(filter, handler) -> Subscription # 事件总线（推模式）—— 让 Event 不止是日志

# —— 读取层（从 Event 投影而来）——
kernel.query_state(selector) -> State
kernel.recall_memory(query, k) -> [Memory]

# —— 行动层（一切对世界的改变都经此，并自动 emit event）——
kernel.invoke_capability(name, args, ctx) -> Result     # 内部：先 request_approval，放行后执行，再 emit CapabilityInvoked
kernel.request_approval(action, risk, ctx) -> Decision

# —— 调度层（动态 Agent 生态）——
kernel.spawn_agent(spec, task_ref) -> AgentHandle        # emit AgentSpawned
kernel.create_task(goal, plan) -> TaskRef                # emit TaskCreated
kernel.kill_agent(handle) -> void                        # emit AgentTerminated
```

### 3.2 每个 ABI 的契约要点

| ABI | 职责 | 是否 emit event | 治理 |
|-----|------|----------------|------|
| `emit_event` | 写入不可变 Event Log（唯一写入口） | 它本身就是 event | — |
| `read_events` | 按序/按因果读取，支撑重放与审计（拉模式） | 否（只读） | — |
| `subscribe_events` | 按 filter 订阅事件流，推送给 handler | 否（只读） | — |
| `query_state` | 读取当前快照（Event 投影） | 否（只读） | — |
| `recall_memory` | 语义召回信念 | 否（只读） | — |
| `invoke_capability` | 唯一对外作用通道 | ✅ `CapabilityInvoked` | ✅ 必经 Approval |
| `request_approval` | 治理裁决 | ✅ `ApprovalGranted/Denied` | — |
| `spawn_agent` | 拉起临时 Agent | ✅ `AgentSpawned` | 按 spec 限定其可用 capability |
| `create_task` | 登记调度单位 | ✅ `TaskCreated` | — |
| `kill_agent` | 销毁 Agent | ✅ `AgentTerminated` | — |

> **为什么 `subscribe_events` 必须进 v1**：没有它，`Projector` / `Trigger` / `Notification` / `Scheduler` 就只能轮询 Event Log——那 Event 永远只是「日志」。有了订阅推送，Event 才真正成为 **Runtime Event Bus**：State 投影器订阅事件实时物化、Trigger 订阅事件实时触发、通知订阅事件实时推送。这是「日志 → 总线」的关键一跳。

### 3.3 ABI 稳定性契约（这是它配叫「ABI」的原因）

- **版本化**：ABI 带版本号，破坏性变更需升主版本。
- **稳定性承诺**：把 GPT-6 / Claude 6 / Gemini 5、把 Brain 换成 Claude Code / Cursor Agent，**这层 ABI 不变**。
- **能力声明而非硬编码**：新接入的 Agent 通过声明所需 capability 接入，而非改 Kernel。

---

## 4. 第一条端到端验证切片（让 spec 可证伪，不空转）

为避免抽象漂移，spec 落地的第一刀只切一个最小闭环：**「创建一个目标」**，全程走 ABI，验证 Event→State 投影链路成立。

```text
1. UI/Agent 调  kernel.emit_event("GoalCreated", {title, ...}, actor="user")
2. Kernel 写入 Event Log（seq+1，不可变）
3. State Projector 消费该事件 → 物化出 goals 表中一行
4. kernel.query_state("goals.active") 能读到这条目标
5. 删库重放：清空 goals 表，replay(events) → goals 完整重建    ← 验证「State 可由 Event 重建」
```

跑通这 5 步，就证明了 Runtime 的核心契约（边界 + 事件溯源）真实成立，而不只是文档。

---

## 5. 落地优先级（按「Event 先于一切」重排）

> 核心原则：**State/Memory 不先做，Event 先做。**（P0–P4 路线图已在 v0.9.0 落地。）

### P0 · 真相与边界
```text
1. 本规格（Runtime Primitive + Kernel Boundary）稳定下来   ← 你正在读的这份
2. Event Log：不可变、有序(seq)、可重放
3. Kernel ABI 最小集：emit_event / read_events / query_state
4. 立起边界：User Space 不再直接 import store
```

### P1 · 投影与治理
```text
5. State Engine：goals/user_profile 改为 Event 投影
6. Memory Engine：派生信念 + confidence + 衰减（接通 local_llm 抽取）
7. Approval Engine：invoke_capability 强制过审，接通前端确认闭环
```

### P2 · 调度与动态 Agent
```text
8. Task/Scheduler：调度单位 + 状态机事件化
9. Agent Runtime：spawn/kill 临时 Agent，跑通一个端到端场景
10. Planner/Critic 作为 User Space 应用接入 ABI
```

---

## 6. Non-Goals（明确不做什么，防止过度平台化）

> # Runtime 不是分布式系统。
> # Runtime 是边界。
>
> 很多人一看到「Runtime」就自动联想到微服务 / 消息队列 / Kafka / K8s，然后把项目复杂度直接拉爆。
> 本规格里的 Kernel 是**逻辑边界**，不是网络边界。请始终记住上面这两行。

一个没有杀手级应用的平台会死。本规格**刻意不要求**：

- ❌ 不要求分布式 / 微服务 —— **单进程单机完全可以是一个合法 Runtime**（Kernel 是逻辑边界，不是网络边界）。
- ❌ 不要求一次性把所有表都改成事件溯源 —— 先让 Event 成为**权威真相来源**，存量投影可渐进迁移。
- ❌ 不要求先造通用平台 —— 先用「目标-复盘」这个**现成垂直场景**当 Runtime 的第一个原生应用，验证原语，再泛化。
- ❌ 不追求接入所有 Agent 框架 —— ABI 稳定即可，接入是水到渠成的事。

> 次序铁律：**先用一个 App 把 Runtime 跑通并跑出价值，再把 Runtime 抽象成平台。** 不能反过来。

---

## 7. 一句话总结

```text
Agent 是功能。Runtime 才是平台。
而 Runtime 的起点不是代码，是这两样东西的定义：
        Runtime Primitive（7 个对象）
        Kernel Boundary（一道边界）
这份文档稳定之后，代码实现只是体力活。
```

W1–W4 宪法冲刺已完成（见附录）。当前重点：**在闭合的 Runtime 上扩展 App**，而非新增 Primitive。

---

## 附录 A — Migration History (W1–W4)

| Sprint | 交付 |
|--------|------|
| **W1** | `check_boundary.py`；`task_engine` / `approval_engine` / `executor` 改 `query_state` |
| **W2** | Agent 热路径 + Goals API 治理读；扩大 boundary 扫描范围 |
| **W3** | 单一执行权威 `invoke_capability`；Memory Chroma 索引迁入 Kernel；Brain 禁 import `mcp_hub` |
| **W4** | `event_log` 为治理域真相；`legacy_event_adapter`；Kernel→Bus bridge |

**验证命令：**

```bash
make boundary          # 与 CI 一致
make boundary-strict   # allowlist 非空时失败
make rebuild-verify
make belief-verify     # Pattern + Belief（本地，未入 CI）
cd backend && python -m pytest tests/ -q
```

**Explicit non-goals（仍未做）：** Conversation/messages 全量 Event Sourcing；`background_tasks` 并入 Task 聚合；`spawn_agent` 移除。
