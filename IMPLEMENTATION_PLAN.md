# Personal AI Runtime · 实现计划（交付给编码模型执行）

> 这份文档把 `RUNTIME_SPEC.md`（v1.0 FROZEN）落成一组**可独立执行的工单（Ticket）**。
> 每个 Ticket 自包含：目标、依赖、要改的文件、详细规格、验收标准、测试。**一个编码模型拿到单个 Ticket 即可在最小上下文下完成它。**
>
> 基线：backend v0.8.0 ｜ Slice 0（内核）已实现并通过 6/6 测试，作为后续一切工作的参考实现与模式来源。

---

## 0. 每个模型开工前必读（Context + 铁律）

### 0.1 必读文件（按顺序）
1. `RUNTIME_SPEC.md` —— 对象模型、边界、ABI 的唯一契约。**不得偏离，不得新增 Primitive。**
2. 参考实现（Slice 0，已通过测试，照它的风格写）：
   - `backend/app/core/runtime/kernel/event.py` —— Event 对象
   - `backend/app/core/runtime/kernel/kernel.py` —— Kernel 与 Event Log、ABI
   - `backend/app/core/runtime/kernel/projectors.py` —— Projector 注册表 + Goal 投影
   - `backend/tests/runtime/test_event_sourcing.py` —— 验证范式
3. 你的 Ticket 涉及的现有代码（每个 Ticket 会列出）。

### 0.2 铁律（GOLDEN RULES，任何 Ticket 都不可违反）
1. **User Space 永不直接碰存储。** API / Agent / Workflow / 调度器一律不得 `import store`、不得执行 SQL、不得读写文件/网络。一切经 Kernel ABI。
2. **一切「改变系统」的操作 = 一次 `kernel.emit_event`。** 没有第二个写入口。
3. **State 是 Event 的投影，永不被直接写。** 只有 `projectors.py` 里的投影器能写读模型表。
4. **Event Log 不可变。** 只 INSERT，永不 UPDATE/DELETE（已由触发器在 DB 层兜底）。
5. **单进程、逻辑边界。** 不引入消息队列 / 微服务 / Kafka / 分布式。Kernel 是逻辑边界，不是网络边界。
6. **不发明概念。** 不新增 Primitive、不加 Layer。`World/User/Preference Model` 都挂在 Memory 之下。
7. **每个 Ticket 必须自带测试**，并保证 `ruff check`、`mypy`、`pytest` 全绿（对齐 `.github/workflows/ci.yml`）。
8. **可重建是验收硬指标**：凡引入新投影，必须能 `kernel.rebuild(aggregate_type)` 后 State 与重建前字节一致。

### 0.3 Kernel ABI 现状（已实现，可直接调用）
```python
kernel.emit_event(type, aggregate_type, aggregate_id, payload=None,
                  actor="system", caused_by=None, correlation_id=None) -> Event
kernel.read_events(aggregate_type=None, aggregate_id=None, type=None,
                   correlation_id=None, since_seq=0) -> list[Event]
kernel.subscribe_events(handler, type=None, aggregate_type=None) -> unsubscribe()
kernel.query_state(selector, **filters) -> list[dict]   # 目前仅 "goals"
kernel.rebuild(aggregate_type) -> int                   # 清空投影 + 重放
```
ABI 待扩充：`invoke_capability` / `request_approval` / `create_task` / `spawn_agent` / `kill_agent`（见下方 Ticket）。

---

## 1. 进度看板

| Ticket | 标题 | 状态 | 依赖 |
|--------|------|------|------|
| S0 | Kernel + Event Log + Goal 投影 + 重建验证 | ✅ DONE | — |
| T1 | 把 Goals API 迁移到 Kernel（边界落到真实功能） | TODO | S0 |
| T2 | Capability + Approval 进 Kernel（敢动手·后端） | TODO | S0 |
| T3 | 前端审批闭环（敢动手·前端） | TODO | T2 |
| T4 | Memory 改造为派生信念（schema + 投影 + 抽取） | TODO | S0 |
| T5 | Task/Agent 生命周期事件化 + 动态 spawn | TODO | T2 |
| T6 | Projector 框架硬化 + CI 重建守卫 | TODO | T1 |

> 推荐执行顺序：T1 → T2 → T3 →（T4 / T6 可并行）→ T5。
> T1 是"边界"在真实功能上的第一次落地，价值与示范意义最高，**强烈建议第一个做**。

---

## 2. Tickets

---

### T1 · 把 Goals API 迁移到 Kernel

**目标**：让真实的 `goals` 功能成为「事件溯源」的第一个生产路径——API 不再直接写表，而是 `emit_event`；读经 `query_state`。这是 GOLDEN RULE #1 在真实功能上的第一次兑现。

**依赖**：S0 ｜ **涉及文件**：`backend/app/api/goals.py`、`backend/app/core/runtime/kernel/projectors.py`

**规格**：
1. 在 `projectors.py` 增加 `GoalDeleted` 投影器（`DELETE FROM goals WHERE id = ?`），并把 `goal` 的 owned table 保持为 `["goals"]`。
2. 改写 `goals.py` 的写路径，全部改成经全局 kernel 实例（新增 `backend/app/core/runtime/kernel_instance.py`，导出单例 `kernel = Kernel()`，供 User Space 调用）：
   - `create_goal` → `kernel.emit_event("GoalCreated", "goal", goal_id, payload={...}, actor="user")`
   - `update_goal` → `GoalUpdated`（payload 仅含变更字段）
   - 「完成目标」语义 → `GoalCompleted`
   - `delete_goal` → `GoalDeleted`
   - 写完后用 `kernel.query_state("goals", ...)` 或按 id 读，返回结果。
3. 读路径（`list_goals`/`get_goal`）改为经 `kernel.query_state`（必要时扩 `query_state` 支持按 id；保持只读、不破坏返回结构）。
4. **删除 `goals.py` 里所有直接 `conn.execute("INSERT/UPDATE/DELETE ... goals ...")`。**
5. 现存 `event_recorder.record(...)`（旧业务事件表）可保留或并行，但**不得**作为 goals 的写入口。

**验收标准**：
- Goals 相关 API 对外行为与字段不变（前端无需改动）。
- `goals` 表只被投影器写。grep 确认 `api/goals.py` 无直接写 SQL。
- 新增集成测试 `tests/runtime/test_goals_event_sourced.py`：经 API/kernel 做「建 3 个、改 1 个、完成 1 个、删 1 个」后，`kernel.rebuild("goal")` 前后 `query_state("goals")` 字节一致。
- `ruff`/`mypy`/`pytest` 全绿。

**不在范围**：actions（行动步骤）暂不迁移，单独 Ticket；前端不动。

---

### T2 · Capability 调用与 Approval 进 Kernel（后端）

**目标**：让"对世界的一切作用"都经 Kernel，并接通治理层。实现 ABI：`invoke_capability` 与 `request_approval`，二者都产生事件。

**依赖**：S0 ｜ **涉及文件**：`kernel.py`、新增 `projectors.py` 的 approval 投影、`backend/app/core/harness/mcp_hub.py`、`backend/app/core/runtime/approval_engine.py`

**规格**：
1. 新增 ABI：
   ```python
   kernel.request_approval(action, risk, ctx, actor, correlation_id=None) -> Decision
   # 依据分级策略裁决：auto_allow / needs_user / forbidden
   # emit "ApprovalRequested" 然后 "ApprovalGranted" 或 "ApprovalDenied"
   kernel.invoke_capability(name, args, actor, correlation_id=None, caused_by=None) -> Result
   # 内部：查 capability 风险等级 → request_approval → 放行才真正执行 MCPHub 工具
   # 成功后 emit "CapabilityInvoked"（payload 含 name/args 摘要/结果摘要/seq）
   # 被拒则 emit "CapabilityDenied"，返回 denied 状态
   ```
2. `aggregate_type` 约定：approval 用 `"approval"`、capability 调用用 `"capability"`（或挂在触发它的 task 上，二选一并写进注释）。
3. 分级授权策略来源：复用现有 `mcp_hub.needs_confirmation(name)`；`needs_confirmation=True` → `needs_user`，其余 → `auto_allow`；预留 `forbidden` 名单（配置项，先留空）。
4. 新增 approval 投影到 `approvals` 表（表已存在于 schema），记录裁决，作为审计读模型。
5. **不改 Brain 的对外行为**（前端闭环在 T3）；本 Ticket 只把能力调用与审批的「内核能力」做出来并可被单测驱动。

**验收标准**：
- 单测 `tests/runtime/test_capability_approval.py`：
  - 低风险能力（如 `get_current_time`）→ 自动放行 → 产生 `CapabilityInvoked` 事件。
  - 高风险能力（如 `write_file`）在"未授权"上下文 → 产生 `ApprovalRequested`，默认 `needs_user` → 返回 pending/denied，**不执行**。
  - 模拟授权通过后 → 执行并产生 `CapabilityInvoked`。
  - 所有路径在 `event_log` 留痕，`read_events(correlation_id=...)` 能拉出完整链路。
- `ruff`/`mypy`/`pytest` 全绿。

**不在范围**：前端 UI（T3）；真正接 Brain 主链路（T3 一并处理）。

---

### T3 · 前端审批闭环（端到端"敢动手"）

**目标**：把"需确认操作"从当前的 `skipped` 死路，接成「弹确认 → 用户批准 → 真正执行」的闭环。

**依赖**：T2 ｜ **涉及文件**：`backend/app/core/agents/brain.py`、`backend/app/api/chat.py`、`frontend/src/components/chat/ChatView.tsx`、`frontend/src/components/chat/ConfirmationDialog.tsx`、`frontend/src/api/client.ts`

**规格**：
1. Brain 遇到高风险工具时，不再直接返回 `skipped`，而是经 `kernel.request_approval`；若 `needs_user`，通过现有 SSE `confirmation_required` 事件把 `{tool_name, tool_args, approval_id, tool_call_id}` 发给前端，并**挂起**该工具调用。
2. 前端 `ChatView` 接入 `ConfirmationDialog`（当前未引用）：收到 `confirmation_required` → 弹框 → 用户 Approve/Deny。
3. 新增"恢复执行"通道：前端 Approve 后调用后端（新 endpoint 或复用流），后端 `kernel` 标记 `ApprovalGranted` 并继续执行该 capability，把结果接回对话流；Deny 则 `ApprovalDenied` 并回告模型"用户拒绝"。
4. 全程经 T2 的 `invoke_capability`，事件留痕。

**验收标准**：
- 手动/E2E：对话中让 AI `write_file`，前端弹确认；Approve → 文件被写、对话继续；Deny → 不写、AI 收到拒绝。
- `confirmation_required` 不再恒为 `skipped`。
- 前端 `tsc --noEmit` 通过；后端 `pytest` 全绿。

**不在范围**：分级授权的设置 UI（后续 Ticket）；回滚/预览（后续）。

---

### T4 · Memory 改造为「派生的可衰减信念」

**目标**：把 Memory 从扁平事实升级为 Spec §1.3 定义的派生信念，且可由 Event Log 重建。

**依赖**：S0 ｜ **涉及文件**：`backend/app/store/database.py`（memories schema 迁移）、`projectors.py`、`backend/app/core/agents/local_llm.py`、`backend/app/core/agents/memory_engine`（现有记忆模块）

**规格**：
1. `memories` 表补列：`confidence REAL DEFAULT 0.5`、`derived_from_event TEXT`、`decayed_at DATETIME`（向后兼容，用 `ALTER TABLE ... ADD COLUMN`，已存在则跳过）。
2. 新增 Memory 投影器：消费 `MemoryDerived` 事件 → 写 `memories`（含 confidence/来源事件）；消费 `MemoryDecayed`/`MemoryRevoked` → 更新/降权。owned table = `["memories"]`。
3. 抽取链路（接通已存在但未接线的 `local_llm`）：通过 `kernel.subscribe_events(handler, type="MessageReceived"/...)` 订阅，对话/事件发生后由本地小模型抽取候选信念 → `kernel.emit_event("MemoryDerived", "memory", mem_id, {...})`。**抽取器在 User Space，只经 ABI。**
4. `recall_memory` ABI：在 kernel 增加只读语义召回（先可基于现有 ChromaDB collection，封装在 kernel 内，User Space 不直连向量库）。

**验收标准**：
- 单测：emit 若干 `MessageReceived` → 触发 `MemoryDerived` → `recall_memory` 能召回；`rebuild("memory")` 后 memories 一致。
- 置信度衰减：emit `MemoryDecayed` 后 confidence 下降并可被召回排序反映。
- CI 全绿。

**不在范围**：World Model/User Model 的高级视图（它们是 Memory 之上的查询，非新对象，后续按需做）。

---

### T5 · Task / Agent 生命周期事件化 + 动态 spawn

**目标**：实现 Spec 的"动态 Agent 生态"最小闭环：Task 是调度单位、Agent 是临时执行单元，生命周期全部事件化。

**依赖**：T2 ｜ **涉及文件**：`kernel.py`、`projectors.py`、`backend/app/core/runtime/task_engine.py`、`backend/app/core/runtime/background_worker.py`、`backend/app/core/agents/planner.py`、`critic.py`

**规格**：
1. ABI：
   ```python
   kernel.create_task(goal, plan, actor, correlation_id=None) -> TaskRef   # emit "TaskCreated"
   kernel.spawn_agent(spec, task_ref) -> AgentHandle                       # emit "AgentSpawned"
   kernel.kill_agent(handle) -> None                                       # emit "AgentTerminated"
   ```
2. Task 状态迁移全部 emit 事件（`TaskStarted`/`TaskCompleted`/`TaskFailed`），`tasks` 表成为投影，`rebuild("task")` 可重建。
3. Agent 为 ephemeral：`spawn_agent` 拉起临时执行单元（先用现有 Brain 作为默认执行后端），限定其可用 capability（经 T2 的授权），完成即 `kill_agent`。**禁止常驻 Agent。**
4. 端到端切片："帮我规划下周项目" → `create_task` → spawn 临时 Planner（产计划）→ Critic 审计 → Executor 在授权边界内执行 → 全部销毁。一个场景跑通即可，不求多。
5. 共享 `correlation_id`：整条链路事件用同一个 trace id，`read_events(correlation_id=...)` 能还原全过程。

**验收标准**：
- 单测/脚本：跑通上述一个端到端场景，链路事件齐全且可 trace；`rebuild("task")` 一致。
- 无常驻 Agent（用完即 `AgentTerminated`）。
- CI 全绿。

**不在范围**：把 `Agent` 升级为 `Execution` Primitive（Spec 标记为 Post-v1，**本 Ticket 不做**）。

---

### T6 · Projector 框架硬化 + CI 重建守卫

**目标**：把"State 可由 Event 重建"从单测保证升级为**架构级守卫**，防止后续 Ticket 偷偷绕过边界。

**依赖**：T1 ｜ **涉及文件**：`projectors.py`、`kernel.py`、`.github/workflows/ci.yml`、新增 `backend/scripts/verify_rebuild.py`

**规格**：
1. `kernel.rebuild_all()`：遍历所有已注册 aggregate_type 重建。
2. 重建守卫脚本：对一组样例事件，重建后对每张投影表做快照对比，任何不一致即非零退出。
3. CI 增加一步：跑重建守卫 + 一条 grep 守卫（断言 `app/api/**` 与 `app/core/agents/**` 不出现对投影表的直接 `INSERT/UPDATE/DELETE`，即边界不被破坏）。
4. （可选）投影快照/检查点机制，避免事件量大时重放过慢——**仅在需要时做，先不过度设计**。

**验收标准**：
- CI 新步骤生效：故意在某 API 里直接写投影表会让 CI 失败。
- 重建守卫脚本可独立运行并通过。

**不在范围**：分布式/快照存储的复杂方案（违反 GOLDEN RULE #5）。

---

## 3. 每个 Ticket 的"完成定义"（DoD）

一个 Ticket 只有同时满足以下才算完成：
1. 行为符合验收标准，自带测试且通过。
2. `ruff check`、`mypy`、`pytest`（含覆盖率）全绿，对齐 `.github/workflows/ci.yml`。
3. 不违反任何 GOLDEN RULE（尤其 #1 边界、#2 单一写入口、#8 可重建）。
4. 不新增 Primitive、不加 Layer、不引入分布式组件。
5. 涉及前端的，`tsc --noEmit` 通过。

---

## 4. 给编排者（你/主模型）的交接提示词模板

把单个 Ticket 丢给编码模型时，建议这样开场：

```text
请阅读仓库根目录 RUNTIME_SPEC.md（契约）与 IMPLEMENTATION_PLAN.md 第 0 节（铁律）。
参考实现见 backend/app/core/runtime/kernel/ 与 tests/runtime/test_event_sourcing.py。
现在只实现 IMPLEMENTATION_PLAN.md 的 <Ticket 编号>，严格遵守 GOLDEN RULES，
完成其"验收标准"并保证 ruff/mypy/pytest 全绿。不要做范围之外的事，不要新增 Primitive。
```

---

## 5. 现状小结

- **S0 已完成并验证**：Kernel / 不可变 Event Log（append-only 触发器）/ Goal 投影 / `rebuild` 重建链路，6/6 测试通过，其中关键用例证明「清空 goals 表后仅靠 Event Log 字节级重建」。
- Runtime 已拥有真正的内核与边界雏形。接下来按 T1→T6 把边界推广到真实功能、接通治理与动态 Agent。
- **核心心法**：每个 Ticket 都在做同一件事——**把又一类「直接改系统」的旧路，改成「emit_event → 投影」的内核路**。做完 T1–T6，这个项目就从 Personal AI App 真正变成 Personal AI Runtime。
