# HISTORY

> 本文档归档已完成的战略里程碑、执行顺序历史与重大工程决策。
> 当前状态见 [CURRENT_STATE.md](CURRENT_STATE.md)，未来方向见 [ROADMAP](../product/ROADMAP.md)。

---

## 战略里程碑总览

Runtime Governance v1 的三个战略里程碑于 **2026-06-17** 全部达成。

| 里程碑 | 达成日期 | 核心标志 |
|--------|---------|---------|
| **M1 · Causal Closure（因果闭环）** | 2026-06-17 | execution_id 运行时执法（D2）、provenance join 门禁（A1b）、后台任务 Execution 链（B1）、forbidden 执法（A3） |
| **M2 · Single Source of Truth（单一真相）** | 2026-06-17 | Trigger 读 event_log（B3）、生产路径零 `INSERT INTO events`（C1）、Inbox/Knowledge 审计事件（B2） |
| **M3 · Runtime v1** | 2026-06-17 | 单轨 AgentManager（C2）、外部 MCP Policy 事件溯源（C3）、Agent 并发隔离（D1） |
| **H1 · Memory 强化** | 2026-06-18 | Pattern/Belief 幂等/质量/存活 CI 守护，INV-P6 升 Tier 1 |

---

## M1 · Causal Closure（因果闭环）

**包含任务**：A1（静态 ownership CI）、A1b（provenance join 门禁）、A3（forbidden 执法）、B1（后台任务 Execution 链）、D2（execution_id 运行时执法）

**达成后系统保证**：

```text
任意 Agent 侧副作用
    → invoke_capability（execution_id 运行时执法）
    → Execution 事件链
    → CapabilityInvoked（caused_by 可追）
    → 治理投影行（反查 event_log）
```

**Invariants 升级**：

| 任务 | Invariant | 变更 |
|------|-----------|------|
| D2 | INV-P1（execution ownership） | Tier 2 → **Tier 1** |
| A1b | INV-P7（provenance） | Tier 2 → **Tier 1** |

**关闭项**：B1（后台任务副作用无归属）、D1b（BackgroundWorker 裸 SQL 热路径）

---

## M2 · Single Source of Truth（单一真相）

**包含任务**：B3（Trigger 读 event_log）、C1（移除遗留 EventBus 热路径）、B2（Inbox/Knowledge 审计事件）

**达成后系统保证**：

```text
所有决策与阈值评估
    → 只读 event_log 和/或治理投影
    → 不存在 APP_STORAGE.events 作为第二真相
    → 生产路径零 INSERT INTO events
```

**关闭项**：D1a（Trigger 读遗留 events 表）、D4（EventBus 双轨）、D1c（Knowledge 无审计）、D1d（Inbox 无审计）

---

## M3 · Runtime Governance v1

**包含任务**：C2（删除 AgentOrchestrator）、C3（外部 MCP Policy 事件溯源）、D1（Agent 并发隔离）

**达成后系统保证**：

```text
单轨 Agent 流水线（AgentManager，无 Orchestrator 双轨）
外部 MCP Policy 可 rebuild（事件溯源）
多 Agent 并发有 CI 测试覆盖（INV-P5 → Tier 1）
```

**关闭项**：D3（AgentOrchestrator 双轨）、TD-5（外部 MCP policy 在内存）

---

## H1 · Memory 语义再推导验证（INV-P6 → Tier 1）

**达成标志（2026-06-18）**：

- `verify_belief_quality.py` 接入 CI：traceability/novelty/actionability 启发式检查
- `verify_belief_survival.py` 接入 CI：survival/revocation/strengthen 统计
- `verify_pattern_idempotency.py` 接入 CI：SHA256 确定性 id 生成校验
- INV-P6 升为 Tier 1

**额外完成项**（A2）：Pattern/Belief/Vector 一致性 CI 门禁，INV-P2、INV-P3 → Tier 1

---

## 执行顺序（A1 → D1 的完整链路）

```text
A1 → A1b → A3 → B3 → A2 → B1 ★ → D2 → B2 → C1 → C2 → C3 → D1
```

| 段 | 含义 |
|----|------|
| A1–A1b–A3 | 执法：execution_id、provenance、forbidden 路径 |
| B3 → A2 | 统一决策层真相 + 认知/向量层 CI |
| B1 ★ | 战略分水岭：后台任务进 Execution 链 |
| D2 | INV-P1 从静态 grep → 运行时行为保证 |
| B2 | Inbox/Knowledge 审计事件 |
| C1 | 单一真相：legacy `events` / EventBus 热路径归零 |
| C2–C3–D1 | 单轨 Agent、Policy 事件溯源、并发隔离 |
| H1 | Memory re-derive 验证，INV-P6 → Tier 1 |

---

## 里程碑与 North Star 对应

```text
M1 ≈ Causality Runtime  → North Star P3（Agent 副作用可审计）
M2 ≈ Truth Runtime      → North Star P1（Event Log 为事实来源）
M3 ≈ Governance Runtime → North Star P4 + P5（授权 + Agent 可替换）
H1 ≈ Memory Re-derive   → North Star P1 + INV-P6
```

---

## 不变量升级记录

| 不变量 | 原 Tier | 新 Tier | 触发里程碑 | 日期 |
|--------|---------|---------|-----------|------|
| INV-P7 | Tier 2 | Tier 1 | M1 (A1b) | 2026-06-17 |
| INV-P1 | Tier 2 | Tier 1 | M1 (D2) | 2026-06-17 |
| INV-P4 | Tier 2 | Tier 1 | M1 (A3) | 2026-06-17 |
| INV-P2 | Tier 2 | Tier 1 | A2 | 2026-06-17 |
| INV-P3 | Tier 2 | Tier 1 | A2 | 2026-06-17 |
| INV-P5 | Tier 2 | Tier 1 | M3 (D1) | 2026-06-17 |
| INV-P6 | Tier 2 | Tier 1 | H1 | 2026-06-18 |

---
