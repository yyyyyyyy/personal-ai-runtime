# Personal AI OS · 产品执行评审 & 未来架构路线图（Runtime 升级版）

> 评审视角：不把它当代码仓库，也不只当 AI Application，而是当作一个**平台（Runtime）**来审视。
> 评审日期：2026-06-09 ｜ 评审对象：backend v0.8.0 / frontend v0.4.0 / desktop v0.7.0
> 版本：v2（在 v1「产品+战略评审」基础上，补齐 Runtime 视角这一最关键的缺失维度）

---

## 〇、一句话结论（升级版）

**v1 的判断（"展厅 vs 住宅"）其实站错了抽象层。**

它不是一座盖了一半的房子，而是 **一块已经打好地基、铺好管线的地皮**。

地皮上现在长出的"聊天 / Agent / 工具"未来都会变；但地下那套管线——`State / Memory / Events / Permissions / Execution / Identity`——是**不随模型和 Agent 范式变化的**。

> **真正的问题不是"功能做完了没"，而是"它到底想成为一个 App，还是一个 Runtime"。**
> 这两条路天花板差一个数量级。这份评审的核心，就是论证第二条路、并给出怎么走。

---

## 一、它现在能帮到使用者什么？（保留 v1 的诚实评估）

### ✅ 真正能用、有差异化价值

| 能力 | 价值 | 为什么有用 |
|------|------|-----------|
| 带上下文的对话 | ★★★★ | `ContextEngine` 把目标/事件/记忆注入每次对话——它"记得你是谁"，这是和裸 ChatGPT 的本质差异。 |
| 目标 / 行动管理 | ★★★★ | 后端逻辑完整 + 前端 UI + 停滞检测。被验证过的刚需。 |
| 本地数据沉淀 | ★★★★★ | 全部落本地 SQLite + ChromaDB，不上云。对"本地使用"定位，这是核心卖点。 |
| 定时简报 / 复盘 | ★★★ | 日/周/月复盘完整，但需后端常驻。 |

### ⚠️ 看起来有、实际没接通（已逐一核验）

| 宣称能力 | 真实状态 |
|---------|---------|
| 多智能体（Planner/Critic/WorldModel/IntentPredictor） | 代码存在，但后端**无任何 import**——"自主规划"是 PPT |
| 写操作审批闭环 | Brain 遇确认操作直接 `skipped`；前端 `ChatView` **未引用 `ConfirmationDialog`**——"动手"能力全部哑火 |
| 本地 LLM 自动记忆抽取 | 已实现，未接入任何流程 |
| MCP 外部服务器 | `mcp_config.json` 被读了但没被使用 |
| 多模型 fallback | `get_fallback_clients()` 从未被调用 |

### ❌ 上手门槛（对个人用户最致命）
- 没有 README、没有一键启动、没有 Docker。普通人**跑不起来**。
- 三端版本号不一致（0.8.0 / 0.4.0 / 0.7.0）。

> 这一章回答的是"今天能用吗"。但**它只看了 App 层**。下面这一章，才是 v1 真正漏掉的东西。

---

## 二、Runtime 视角下的项目评估（v1 缺失的最关键一章）

### 2.1 v1 站在了错误的抽象层

v1 全程在讨论 **Agent 层**：Planner、Critic、Trigger、Memory、World Model……
但从头到尾没问一个更底层的问题：

> **这些 Agent，是跑在什么东西上的？**

v1 的隐含架构是一代 Agent 系统：

```text
User → Chat → Agent → Tools
```

而正确的架构，是把 Agent 从"核心"降级为"应用"：

```text
User → Runtime → Agent → Tools
```

**Agent 不是核心，Runtime 才是。**

### 2.2 为什么 Runtime 比 Agent 重要：因为 Agent 一直在变，Runtime 不变

```text
2024  Prompt
2025  Workflow
2026  Agent
2027  Multi-Agent
2028  ???
```

Agent 范式每年换一次。但底下这些东西不会变：

```text
State / Memory / Events / Permissions / Identity / Execution / Audit
```

类比成熟工业：

```text
浏览器会变，网页会变 —— OS 不会变
模型会变，Agent 会变 —— Runtime 不会变
```

未来你想把 Claude Code / Cursor Agent / OpenAI Agent / Gemini Agent 全部接进来，**稳定的不是 Agent，而是它们共同依赖的那层 Runtime 原语**。

### 2.3 关键洞察：这个项目已经**长出了 Runtime 雏形**（用代码逐层对照）

这是这个项目最被低估的价值。它不是"又一个聊天套壳"，因为它已经把数据建模成了 **Runtime 原语**，而不是业务表：

| Runtime 层 | 现有代码 | 它其实是什么 |
|-----------|---------|------------|
| **State Layer** | `goals` `actions` `events` `memories` `user_profile` | 不是聊天记录，而是 **Runtime State**（"我是谁、我在做什么"） |
| **Event Layer** | `activity_log` `telemetry` `triggers` `notifications` `EventBus` | 不是业务表，而是 **Event Bus**（"世界发生了什么"） |
| **Capability Layer** | `Tool Registry` `MCPHub` `Integrations` | 不是工具集，而是 **Capability Runtime**（"我能做什么"） |
| **Governance Layer** | `ApprovalEngine` `needs_confirmation` `audit/activity_log` | 不是确认弹窗，而是 **Permission System**（"我被允许做什么"） |
| **Execution Layer** | `TaskEngine` `StateManager` `BackgroundWorker` `Scheduler` | 不是任务列表，而是 **执行内核雏形**（"如何可靠地跑完一件事"） |
| **Agent Layer** | `Planner` `Critic` `Executor` | **只是跑在 Runtime 上的一种应用**，不是地基 |

因此项目未来的形态不该是：

```text
Personal AI OS
 └─ Agent
```

而应该是：

```text
Personal AI Runtime
 ├─ Identity
 ├─ State
 ├─ Memory
 ├─ Events
 ├─ Permissions
 ├─ Capabilities (Tools)
 └─ Agents   ← 只是 Runtime 上的插件
```

### 2.4 但是——它现在只有"原语的素材"，还没有"Runtime 的内核"（我补的关键判断）

> 这是我对你框架的最重要补充。**承认它有 Runtime 雏形，但要诚实：雏形 ≠ Runtime。**

一个真正的 Runtime / OS，和"一堆建模得不错的表"之间，差的是 **三样内核级的东西**，而这三样目前都缺：

#### ① 缺一个稳定的"系统调用层"（Syscall / Kernel ABI）
现在 Brain、Planner、各 API **直接读写 SQLite / ChromaDB**。这相当于应用程序直接读写磁盘扇区、绕过了操作系统。
真正的 Runtime 必须有一层**稳定的内核接口**：Agent 不碰存储，只调用 `runtime.state.get()` / `runtime.memory.recall()` / `runtime.capability.invoke()` / `runtime.approval.request()`。
**只有当 Agent 编程的对象是"这套 ABI"而不是"具体的表和工具",换掉 GPT-6 / Claude 6 / 任何 Agent 框架时,下面才纹丝不动。** 这才是"OS 不变"的真正含义。

#### ② 缺一个拥有 Agent 生命周期的"调度内核"
现在 Agent 是被直接 import、全局共享状态的"函数集合"，不是被内核 spawn / suspend / kill 的"进程"。
`BackgroundWorker` + `TaskEngine` + `StateManager` 是内核调度器的**前身**，但还没有形成"内核拥有 Agent 生命周期"的控制反转。

#### ③ 缺隔离与多租户（Isolation）
多个 Agent 当前会共享同一份全局可变状态，没有会话/能力沙箱。Runtime 的本质之一就是**隔离**——一个 Agent 崩了、越权了、跑飞了，不能污染整个系统。

> **小结**：项目当前处于"有 Runtime 的**数据模型**，但没有 Runtime 的**内核**"的阶段。
> 好消息是：素材选对了，方向对了。坏消息是：把"原语"焊成"内核 ABI"，是接下来最该做、也最难做、但护城河最深的一件事。

---

## 三、最终形态：从「四层」升级为「五层」（Runtime 作为 Layer 0）

v1 给出的四层（Self / Agency / Autonomy / Trust）是对的，但**少了最底下那层**。补上 Layer 0 之后：

```text
Layer 4  Trust        信任与隐私基座（本地优先 / 数据主权 / 可问责）
Layer 3  Autonomy     自主后台心智（感知-推演-行动循环）
Layer 2  Agency       可信执行体（分级授权 / 可解释 / 可回滚）
Layer 1  Self         持久人格内核（自动生长的世界模型）
Layer 0  Runtime      ← 新增：不依赖任何模型的执行基座
```

### Layer 0 · Runtime（最关键的新增层）

它回答六个**与模型无关**的问题：

| 原语 | 回答的问题 |
|------|-----------|
| **Identity** | 我是谁 |
| **State** | 我当前处于什么状态 |
| **Memory** | 我过去发生过什么 |
| **Events** | 世界发生了什么 |
| **Permissions** | 我允许 AI 做什么 |
| **Execution** | 如何可靠执行 |

> 这一层的判定标准只有一句话：**把 GPT-6 / Claude 6 / Gemini 5 全部换掉，这一层仍然原封不动地存在。**
> 满足这句话，它才是 OS；不满足，它只是一个绑定了某代模型的 App。

### Layer 1–4 沿用 v1（略作收敛）
- **Layer 1 Self**：记忆**自动生成 + 自动遗忘**（带置信度衰减），而不是手动 CRUD。`Memory v2 UserProfile` + `local_llm` 已选对方向，只差接通。
- **Layer 2 Agency**：分级授权 + 可解释 + 可回滚。`needs_confirmation` / `ApprovalEngine` 是雏形。
- **Layer 3 Autonomy**：持续运行的"观察→更新世界模型→推演→行动/提醒"循环。`TriggerEngine` + `BackgroundWorker` 的目标态。
- **Layer 4 Trust**：本地优先、端侧推理、完整数据主权。这是长期护城河。

---

## 四、修正 v1 的一处误判：未来不是「固定多智能体团队」，而是「动态 Agent 生态」

v1 写「多智能体社会是未来形态」。**这个判断很可能是错的，我修正它。**

错在哪：它默认了一支 7×24 常驻的固定 Agent 团队（Planner / Critic / Researcher / Writer 永久存在）。

```text
❌ 旧设想：固定 Agent 团队，长期常驻
   Planner / Critic / Researcher / Writer  →  7×24 永久存在
```

但 **Agent 的本质是上下文窗口，不是进程**。它廉价、短命、可被随时创建和销毁。所以更可能的未来是：

```text
✅ 动态 Agent 生态（Dynamic Agent Ecosystem）
   Task → Runtime → 按需生成临时 Agent Group → 完成 → 销毁
```

**Runtime 是持久的，Agent 是 ephemeral 的。** Runtime 持有所有持久状态（State/Memory/Permissions），Agent 只是被内核临时拉起、用完即弃的 worker。

这也正好印证了第二章 §2.4 的判断：**之所以需要"调度内核 + 稳定 ABI",就是为了支撑这种"按需 spawn / kill"的动态生态。** 固定团队不需要内核，动态生态才需要。

---

## 五、投资人视角：护城河在哪？（我对你这段做一处关键锐化）

如果我是投资人，我**不会**看这些——它们没有护城河，全部可复制：

```text
22 Tools / 18 Tables / 13 APIs   ← 一周能抄完
Agent Prompt / Workflow          ← 一天能抄完
Claude Code / Cursor 的能力       ← 大厂随时复制
```

我会看 **Runtime**。但这里我要给你的论断打一个补丁，因为它有个常见但致命的偏差：

> **你说"你的 Runtime 复制不了"。**
> **不对——Runtime 的*代码*完全可以被复制。真正复制不了的，是 Runtime 里沉淀下来的 *State*。**

护城河的精确表述应该是：

| 层次 | 能否被复制 | 是否护城河 |
|------|-----------|-----------|
| Agent / Prompt / Tools | 能，几天 | ❌ |
| Runtime **架构与代码** | 能，几个月（架构思想甚至会被公开） | ⚠️ 仅时间窗口 |
| Runtime 里**用户的累积 State**（世界模型、记忆、授权、历史） | **不能** | ✅✅✅ 真护城河 |

原因：用户在你的 Runtime 上跑得越久，他的 `State / Memory / Identity` 越厚，**迁移成本越高、对你的依赖越深**。这才是真正的资产——它和数据库护城河、个人云护城河是同一种东西，只不过这里沉淀的是"一个人的数字自我"。

> **所以投资人真正该问的是：这个 Runtime 是否让用户的个人 State 持续、独占地沉淀下来，并且越用越难离开？**
> Runtime 是平台，**Runtime 里的个人 State 才是平台的网络效应**。

---

## 六、如果由我接手：Runtime-First 的迭代路线（重排 v1 优先级）

> v1 的路线是 **App-first**（先接审批、再接 Agent）。Runtime 视角下，必须重排：**先把原语焊成内核 ABI，Agent 才能变成可插拔的插件。**
> 但也要避免另一个极端——**过早平台化**（详见 §6.5 风险）。

### P0（1–2 周）· 让它能跑 + 立起 Runtime 地基
1. **README + 一键启动**（`docker-compose up` / `make dev`）。跑不起来 = 帮助为零，这条永远第一。
2. **先定义对象模型，再定义 API（顺序不能反）**：详见 `RUNTIME_SPEC.md`。
   - 先把 7 个 Runtime Primitive（Event / State / Memory / Capability / Approval / Task / Agent）和 Kernel Boundary 定义清楚；
   - **Event 先于一切**：先把 `events` 表升级成不可变、有序(seq)、可重放的 Event Log（State/Memory 都能从它重建，唯独它丢了不可逆）；
   - 再立 `kernel.emit_event / read_events / query_state` 最小 ABI，并立起铁律：**User Space 不再直接 `import store`**。

### P1（2–4 周）· 把"敢动手"做成内核能力，而非 App 补丁
3. **Permission System 收口**：让 `ApprovalEngine` 成为 `runtime.approval` 的唯一实现，Brain 不再自己判断 `skipped`。前端 `ChatView` 接通 `ConfirmationDialog` 形成闭环，审批落 `approvals` 表（= 内核级 audit）。
4. **分级授权**：只读 / 低风险自动 / 高风险确认 / 永不允许，配置在 Runtime 层而非散落在工具里。

### P2（3–5 周）· 调度内核 + 动态 Agent
5. **把 Agent 改造成"内核 spawn 的进程"**：`BackgroundWorker` + `TaskEngine` 升级为能 spawn / suspend / kill 临时 Agent Group 的调度器。先跑通**一个**端到端场景（如"规划下周项目"：Runtime 按需拉起 Planner+Critic+Executor → 在授权边界内执行 → 销毁）。
6. **接通 `TriggerEngine` + `broadcast_notification`**：后台感知（停滞目标/deadline/邮件积压）→ 推送桌面通知（Electron 接收端已就绪，只差生产者）。

### P3（持续）· 让 State 自动生长（护城河变深）
7. 接通 `local_llm` 自动记忆抽取，让 `user_profile` 自动更新——**这一步直接决定 §5 的护城河厚度**。
8. `WorldModel` 30 天快照喂给 `ContextEngine`，上下文从"列举事实"升级为"理解趋势"。

### P4（差异化）· Trust 层
9. Ollama 成为敏感操作默认路径；完整数据主权工具（导出/迁移/销毁）。
10. 补集成测试（现仅 3 个 runtime 单测，无 Brain/MCP/API 测试）。

### 6.5 我必须提醒的反向风险：不要「过早平台化」
> 这是对"all-in Runtime"最重要的制衡。

**一个没有杀手级应用的平台会死。** 如果一上来就追求"通用 Runtime / 接入所有 Agent 框架"，很可能造出一个优雅但没人用的抽象层。正确的次序是：

```text
薄 Runtime  +  一个做到惊艳的垂直场景（如"目标-复盘"闭环）
        ↓ 用这个场景验证 Runtime 原语
        ↓ 再逐步把原语泛化、对外开放
```

**先用一个 App 把 Runtime 跑通、跑出价值，再把 Runtime 抽象出来当平台。** 而不是反过来。这个项目的好处恰恰是：它已经有"目标/复盘"这个现成的垂直场景，可以拿来当 Runtime 的第一个"原生应用"。

### 我不会做的事
- ❌ 不再加新概念模块。广度够了，现在是还债 + 收口的时候。
- ❌ 不追全功能集成（一堆半成品 SaaS 接入）。
- ❌ 不为了"平台"而平台——必须有一个 App 在上面真正跑起来并产生价值。

---

## 七、优先级总览（一页纸）

| 优先级 | 事项 | Runtime 层 | 为什么 |
|--------|------|-----------|--------|
| 🔴 P0 | README + 一键启动 | — | 跑不起来=帮助为零 |
| 🔴 P0 | Runtime Primitive + Kernel Boundary + Event Log（见 `RUNTIME_SPEC.md`） | Layer 0 | 模型/Agent 可换、地基不动的前提；Event 是唯一不可重建的真相 |
| 🟠 P1 | Permission System 收口 + 审批闭环 | Layer 0/2 | "敢动手"做成内核能力 |
| 🟠 P1 | 调度内核 + 动态 Agent（一个端到端场景） | Layer 0/3 | 支撑"按需 spawn/kill"生态 |
| 🟡 P2 | 后台感知 + 通知推送 | Layer 3 | "会主动" |
| 🟡 P2 | 自动记忆抽取（local_llm） | Layer 1 | 直接决定护城河厚度 |
| ⚪ P3 | 本地优先 + 数据主权 + 集成测试 | Layer 4 | 长期信任 |

---

## 八、最终结论（v2 升级版）

v1 说："这是一座展厅，不是住宅。"——**这个比喻错在抽象层，撤回。**

更准确的表述：

> **这不是一座展厅，而是一块已经打好地基、铺好管线的地皮。**

很多人看到的是上面的"聊天 / Agent / 工具"——这些未来都会变。
真正有价值的，是它已经隐约长出了一组 **Runtime 原语（Runtime Primitives）**：

```text
Identity / State / Memory / Events / Permissions / Execution
```

两条路，天花板差一个数量级：

- **沿 Agent 产品方向走** → 会成为一个**不错的 Personal AI Assistant**（功能层）。
- **沿 Runtime 方向走** → 有机会成为 **Personal AI Runtime —— 一个承载未来所有 Agent / Workflow / Copilot / 数字分身的个人执行平台**（平台层）。

从 `Prompt → Workflow → Agent → Runtime` 这条演进脉络看，第二条路的天花板远高于第一条。

> **Agent 是功能，Runtime 才是平台。**
> v1 已经把功能层看清楚了，但没看到平台层。v2 补上了平台层。
>
> 而要真正落到平台，还差最后一步、也是最硬的一步——
> **把现在散落在表和类里的"原语素材"，收口成一套换掉任何模型都不动的内核 ABI。**
> 这一步做完，它就从"一个记得你的 AI 助手"，变成"一个属于你的、可以承载未来一切 Agent 的个人操作系统"。
