# Personal AI Runtime · 架构规格（RUNTIME_SPEC）

> 这份文档定义把项目从 **Personal AI App** 扭转成 **Personal AI Runtime** 的两块地基：
> **① Runtime Primitive（对象模型）** 和 **② Kernel Boundary（边界）**，最后才是 **③ Kernel ABI**。
> 顺序不能反——先有严格定义的对象，API 才有意义。
>
> 适配代码基线：backend **v0.9.0**

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

> 唯一铁律：
> **Agent 处于 User Space，只能调用 Kernel ABI；只有 Kernel 处于 Kernel Space，独占对存储与外部世界的访问权。**

**当前实现：** User Space 经 `kernel.emit_event` / `query_state` / `invoke_capability` 访问治理域；`backend/scripts/check_boundary.py` 在 CI 门禁，Boundary Debt = 0。

---

## Governance Charter

Runtime 存在的目的是**治理个人 Agent 的行为**，不是提供功能。

- Features are Apps. Governance is Runtime.
- **Facts vs interpretation:** Runtime 提供事实（`query_state`、`read_events`）。Apps 提供解释（brief、review、dashboard、score）。
- Runtime Read Surface = `query_state()` + `read_events()`。聚合、排序、叙事、指标属于 Apps，不进 Kernel。
- 强制：`check_boundary.py`（CI）——`kernel/` 之外的治理域投影读写会让构建失败。

**Maintainer lint:** 这个改动是否需要修改某个 Primitive 的 MUST 语义？否 → App / Capability / Projection / Policy；是 → 需走 RFC。

---

## 1. Runtime Primitive（对象模型 · 先定义对象，不定义 API）

Runtime 由 **7 个原语对象**构成。先把每个对象「是什么」定义到不可争辩，再谈接口。

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

**为什么 Event 必须最优先：**

```text
State      = 当前结果   → 可以从 Event 重建
Memory     = 历史摘要   → 可以从 Event 重建
World Model = 趋势推演   → 可以从 Event 重建
———————————————————————————————————
Event Log  = 真相       → 丢了就永久丢失，无法重建
```

一切的起点是**不可变、有序的 Event Log**，它是 Runtime 的「黑匣子」。

**Event schema（已实现）：**

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

- **追加唯一性**：只允许 INSERT，**永不 UPDATE / DELETE**。
- **`aggregate_type + aggregate_id`** 让同聚合事件天然归并，`rebuild(goal-123)` 顺序重放即可。
- **`caused_by`**（因果上一跳）与 **`correlation_id`**（整条追踪链）是两种不同关系，缺一不可。

### 1.2 State（状态）—— 当前事实快照

```text
定义：用户/系统当前的事实状态
属性：可变、可覆盖、只保留最新值（point-in-time snapshot）
本质：它是 Event 流的「物化视图（materialized view）」
```

**关键承诺**：State 不是被「直接写」的，而是 Event 的投影。`GoalCreated` → `goals` 里一行；`CityChanged` → 覆盖 `state.city`。可被 `replay(events)` 完整重建。

### 1.3 Memory（记忆）—— 派生的、可衰减的信念

必须把 Memory 和 Event 切开：

```text
Event  = 原始真相    「用户在对话里说：我最近在学 Rust」（系统级、客观、不可变）
Memory = 派生信念    「用户偏好 Rust」 confidence=0.8（语义级、主观、可衰减、可推翻）
```

- 记录追加写（保留来源可追溯），携带 confidence，会随时间衰减、被新证据更新或推翻。
- 可向量检索（语义召回）。整个 Memory 集合可由 Event Log 重新抽取重建。

> **Event / State / Memory 三者正交、不重叠：**
>
> ```text
> Event   = 发生过什么   →  Truth        （真相，不可变）
> State   = 现在是什么   →  Projection   （投影，可重建）
> Memory  = 系统相信什么 →  Belief       （信念，可重建、可衰减）
> ```
>
> 未来不需要再为 `World Model` / `User Model` / `Preference Model` 发明新对象——它们都是 Memory 的不同视图。

### 1.4 Capability（能力）—— 与世界交互的接口

```text
定义：Runtime 对外部世界的一切交互接口
属性：声明式注册表，每个能力声明其风险等级与所需授权
例子：filesystem / browser / email / calendar / shell / git
```

`MCPHub` 注册 **23** 个工具；User Space 经 `kernel.invoke_capability` 调用；高风险工具带 `needs_confirmation`。

### 1.5 Approval（审批）—— 能力调用的治理层

```text
定义：对「某次能力调用是否被允许」的治理裁决
属性：裁决一旦做出即不可变（落审计）；裁决前可挂起等待
裁决来源：分级授权策略（自动放行 / 需用户确认 / 永久禁止）
```

Brain 经 `invoke_capability` 挂起待审批；前端 `resolve_approval` 闭环；裁决走 `kernel.grant_approval` / `deny_approval`。

### 1.6 Task（任务）—— Runtime 的调度单位

```text
定义：Runtime 调度的最小单位，承载「要完成的一件事」
属性：状态机（pending → running → done/failed/suspended），可被 Event 重建
```

### 1.7 Agent（智能体）—— 临时执行单元

```text
定义：为完成某个 Task 而被 Kernel 临时拉起的执行单元
属性：ephemeral（短命）—— 用完即销毁，是「上下文窗口」，不是「进程常驻」

✅ 正确模型：Task → Kernel spawn 临时 Agent(s) → 完成 → 销毁
❌ 错误模型：Planner/Critic/Researcher 7×24 永久常驻
```

> 未来是**动态 Agent 生态**，不是固定 Agent 团队。Agent 短命可替换（今天 Brain、明天 Claude Code / Cursor Agent），所以**稳定的必须是它们脚下的 Kernel**。

---

## 2. Kernel Boundary（边界 · 什么能直接访问，什么必须走 Kernel）

### 2.1 两个空间

| 空间 | 谁在这里 | 权限 |
|------|---------|------|
| **Kernel Space** | Event Log、State/Memory 投影器、Capability 注册表、Approval 策略引擎、Scheduler | **独占**访问存储（SQLite/ChromaDB）与外部世界（文件/网络/邮件…） |
| **User Space** | 一切 Agent、Workflow、Planner、Critic、未来接入的 Agent、UI | **只能调用 Kernel ABI**，不持有任何存储句柄 |

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

设计为 **`kernel.verb()` 形态**。唯一稳定的是 Kernel——就像应用最终都走 Linux Syscall，而不是各自访问磁盘。

### 3.1 核心 ABI（最小完备集）

```text
# —— 真相层 ——
kernel.emit_event(type, aggregate_type, aggregate_id, payload, actor, caused_by, correlation_id) -> EventRef
kernel.read_events(filter, since_seq) -> [Event]         # 重放 / 投影 / 审计（拉模式）
kernel.subscribe_events(filter, handler) -> Subscription # 事件总线（推模式）

# —— 读取层（从 Event 投影而来）——
kernel.query_state(selector) -> State
kernel.recall_memory(query, k) -> [Memory]

# —— 行动层（一切对世界的改变都经此，并自动 emit event）——
kernel.invoke_capability(name, args, ctx) -> Result      # 先 request_approval，放行后执行，再 emit CapabilityInvoked
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
| `read_events` | 按序/按因果读取，支撑重放与审计 | 否（只读） | — |
| `subscribe_events` | 按 filter 订阅事件流，推送给 handler | 否（只读） | — |
| `query_state` | 读取当前快照（Event 投影） | 否（只读） | — |
| `recall_memory` | 语义召回信念 | 否（只读） | — |
| `invoke_capability` | 唯一对外作用通道 | ✅ `CapabilityInvoked` | ✅ 必经 Approval |
| `request_approval` | 治理裁决 | ✅ `ApprovalGranted/Denied` | — |
| `spawn_agent` | 拉起临时 Agent | ✅ `AgentSpawned` | 按 spec 限定可用 capability |
| `create_task` | 登记调度单位 | ✅ `TaskCreated` | — |
| `kill_agent` | 销毁 Agent | ✅ `AgentTerminated` | — |

### 3.3 ABI 稳定性契约

- **版本化**：ABI 带版本号，破坏性变更需升主版本。
- **稳定性承诺**：换底层模型、把 Brain 换成 Claude Code / Cursor Agent，**这层 ABI 不变**。
- **能力声明而非硬编码**：新接入的 Agent 通过声明所需 capability 接入，而非改 Kernel。

---

## 4. 端到端验证切片（让 spec 可证伪）

最小闭环：**「创建一个目标」**，全程走 ABI，验证 Event→State 投影链路成立。

```text
1. UI/Agent 调  kernel.emit_event("GoalCreated", {title, ...}, actor="user")
2. Kernel 写入 Event Log（seq+1，不可变）
3. State Projector 消费该事件 → 物化出 goals 表中一行
4. kernel.query_state("goals.active") 能读到这条目标
5. 删库重放：清空 goals 表，replay(events) → goals 完整重建    ← 验证「State 可由 Event 重建」
```

验证命令：

```bash
make boundary          # Kernel 边界守卫（与 CI 一致）
make rebuild-verify    # Event → State 重建验证
make export-roundtrip-verify  # 无损导出/导入往返
cd backend && python -m pytest tests/ -q
```

---

## 5. Non-Goals（明确不做什么，防止过度平台化）

> # Runtime 不是分布式系统。Runtime 是边界。

- ❌ 不要求分布式 / 微服务 —— **单进程单机完全可以是一个合法 Runtime**（Kernel 是逻辑边界，不是网络边界）。
- ❌ 不要求一次性把所有表都改成事件溯源 —— 先让 Event 成为**权威真相来源**，存量投影可渐进迁移。
- ❌ 不要求先造通用平台 —— 先用现成垂直场景验证原语，再泛化。
- ❌ 不追求接入所有 Agent 框架 —— ABI 稳定即可。

> 次序铁律：**先用一个 App 把 Runtime 跑通并跑出价值，再把 Runtime 抽象成平台。** 不能反过来。

---

## 6. 一句话总结

```text
Agent 是功能。Runtime 才是平台。
Runtime 的起点不是代码，是 Runtime Primitive（7 个对象）+ Kernel Boundary（一道边界）的定义。
当前重点：在闭合的 Runtime 上扩展 App，而非新增 Primitive。
```
