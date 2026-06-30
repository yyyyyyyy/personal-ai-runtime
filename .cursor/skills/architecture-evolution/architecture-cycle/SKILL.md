---
name: architecture-evolution/architecture-cycle
description: Workflow orchestrator for the Architecture Evolution cycle. MUST call 00-runtime-controller FIRST before making any recommendation. Does NOT execute logic. ONLY outputs the next recommended skill after validation by the runtime controller. Use as the entry point to navigate the 5-stage evolution pipeline.
---

# Architecture Cycle — Workflow Orchestrator

## 核心职责

**唯一职责**: 根据 Runtime Controller 的授权，决定下一个应执行的阶段。

本 Skill 不执行任何逻辑，不产生任何工件，不修改任何文件。

## 运行时控制器依赖（CRITICAL）

```
┌─────────────────────────┐
│ 00 RUNTIME CONTROLLER   │  ← 必须先调用
│ (硬执行状态机)          │
└───────────┬─────────────┘
            │ EXECUTION_ALLOWED
            │ NEXT_ALLOWED_STAGE
            ▼
┌─────────────────────────┐
│ architecture-cycle      │  ← 编排器（本 Skill）
│ (输出建议)              │
└─────────────────────────┘
```

**在执行任何决策之前，本 Skill 必须**:

1. 读取 `docs/engineering/RUNTIME_STATE.json`
2. 若文件不存在 → 建议调用 `00-runtime-controller` 先初始化状态
3. 若 `active == true` → 不推荐新阶段，报告当前活跃阶段
4. 若 `active == false` → 根据 `current_stage` 和 `next_allowed_stage()` 确定推荐

## 硬约束

- **必须先调用 Runtime Controller**: 不自作主张
- **必须尊重 EXECUTION_ALLOWED**: 只推荐被授权阶段
- **禁止执行任何阶段逻辑**: 只做路由决策
- **禁止产生输出文件**: 只输出建议文本
- **禁止跨阶段操作**: 不混合阶段调用
- **禁止绕过状态机**: 不直接推荐阶段而不检查状态

## 执行流程（更新版）

### 步骤 -1: 变更价值闸门（启动新循环前必须先评估）

在推荐启动一个**新循环**（current_stage=05 completed 或 IDLE after cycle）之前，必须评估自上一轮 TRUTH_AUDIT 的 `last_commit_sha` 起是否有**实质性代码变更**：

```bash
git diff <last_audit_commit>..HEAD --stat -- backend/app/
```

| diff 结果 | 推荐 |
|-----------|------|
| 有 `backend/app/` 源码变更（非纯注释） | 启动新循环（可用增量模式，见 01-truth-audit） |
| 仅文档 / 测试 / 注释变更 | **建议 SKIP 循环** — 报告"无实质架构变更，循环空转无价值"，推荐执行 IMPLEMENTATION_PLAN 中的待办 PR 而非重跑审计 |
| 零 diff | **拒绝启动** — 报告"代码未变，上一轮 artifact 仍然有效" |

理由：流水线的价值在于**响应代码变化**。在零/微小变更上重跑 5 阶段只会翻新时间戳、churn 文档，违背"降低认知负荷"的初衷。闸门让流水线知道何时**不该**运行。

### 步骤 0: 状态获取（必须先执行）

读取 `docs/engineering/RUNTIME_STATE.json`。

```json
{
  "state_machine_version": "1.0.0",
  "current_stage": "01_TRUTH_AUDIT",
  "active": false,
  "cycle_count": 1
}
```

### 步骤 1: 状态分析

| 场景 | active | current_stage | 操作 |
|------|--------|---------------|------|
| 首次运行 | false | IDLE | 建议 01-truth-audit |
| 新循环（cycle_count ≥ 1） | false | IDLE | 建议 01-truth-audit，**并提示其先消化上一轮 VERIFICATION_REPORT 的 "FACT Corrections" 节**，不得重复同一误判 |
| 阶段完成 | false | 01_TRUTH_AUDIT | 验证门禁 → 建议 02 |
| 阶段完成 | false | 02_CONSTITUTION_UPDATE | 验证门禁 → 建议 03 |
| 阶段完成 | false | 03_IMPLEMENTATION_EVOLUTION | 进入 **PR 执行阶段**（见下），而非直接 04 |
| PR 执行中 | false | 03_IMPLEMENTATION_EVOLUTION | PR 尚未全部执行 → 推荐执行下一个 PR（经 `dev-loop` skill），不推荐 04 |
| PR 执行完成 | false | 03_IMPLEMENTATION_EVOLUTION | IMPLEMENTATION_PLAN 中至少 1 个 PR 已合并且 CI 通过 → 建议 04 |
| 阶段完成 | false | 04_REALITY_VERIFICATION | 验证门禁 → 建议 05 |
| 阶段完成 | false | 05_REALITY_SYNC | 循环 → 建议 01 |
| 阶段进行中 | true | {any} | 报告活跃阶段，不推荐 |
| 失败恢复 | false | IDLE (after failure) | 建议 01-truth-audit |
| 被封锁 | false | BLOCKED | 报告封锁原因 |

### 步骤 1.5: PR 执行桥（03 → 04 之间的缺失环节）

`03-implementation-evolution` 只**输出 PR 计划**（禁止改代码）；`04-reality-verification` 验证**代码现实**。两者之间必须有真实的代码执行，否则 04 永远验证的是未改变的代码。

**职责归属**：PR 的实际执行由 `dev-loop` skill 承担（每次执行一个 PR：改代码 → 测试 → CI → 提交，停在 review gate，不自动合并）。

**桥接规则**：
- `03_IMPLEMENTATION_EVOLUTION` 完成后，**不直接转 04**。先进入 PR 执行循环：
  - 对 IMPLEMENTATION_PLAN 中的 PR，按依赖顺序逐个调用 `dev-loop` 执行
  - 每个 PR 执行后 CI 必须通过才能进入下一个
- 只有当**至少一个 PR 真正改变了代码并合并**后，04 才有验证对象，方可推荐 `04-reality-verification`
- 04 的 `Code Commit SHA` 必须 > 03 完成时的 commit（证明代码确实变了），否则 04 的新鲜度门禁失败（见 00-runtime-controller 步骤 3）

### 步骤 2: 门禁验证

对当前阶段完成状态的下一阶段进行门禁检查：

| 当前阶段 | 门禁检查 |
|----------|----------|
| 01_TRUTH_AUDIT (done) | `docs/engineering/TRUTH_AUDIT.md` 存在 + 内容有效 |
| 02_CONSTITUTION_UPDATE (done) | `docs/CONSTITUTION.md` + `docs/ARCHITECTURE_BUDGET.md` 存在 |
| 03_IMPLEMENTATION_EVOLUTION (done) | `docs/engineering/IMPLEMENTATION_PLAN.md` 存在 + PR 已执行 |
| 04_REALITY_VERIFICATION (done) | `docs/engineering/VERIFICATION_REPORT.md` 存在 + Verdict ≠ NON-COMPLIANT |
| 05_REALITY_SYNC (done) | 循环，无门禁 |

### 步骤 3: 授权检查

根据 Runtime Controller 的 `next_allowed_stage()` 验证推荐是否合法。

若推荐被拒绝 → 输出拒绝原因并建议修正路径。

### 步骤 4: 输出决策

```markdown
# Architecture Cycle Decision

## Runtime State (from 00-runtime-controller)

| Field | Value |
|-------|-------|
| CURRENT_STAGE | `{value}` |
| ACTIVE | `{true/false}` |
| CYCLE_COUNT | `{N}` |
| NEXT_ALLOWED_STAGE | `{stage_id}` |
| EXECUTION_ALLOWED | `{true/false}` |

## Gate Verification

| Gate | Condition | Status |
|------|-----------|--------|
| 门禁条件描述 | 具体条件 | ✅ MET / ❌ NOT MET |

## Decision

**Recommended Next Stage**: `{stage_id}`

**Rationale**: <基于状态和门禁的推理>

## Action

1. Confirm Runtime Controller has authorized `{stage_id}`
2. Invoke skill: `architecture-evolution/{stage_id}`
3. After execution, report completion to Runtime Controller

## Pre-flight Checklist

Before invoking the recommended stage, verify:
- [ ] Runtime Controller has authorized this stage (RUNTIME_STATE.json: active=false, current_stage allows transition)
- [ ] All required inputs for the stage are present
- [ ] No stage is currently in progress (active=false)
- [ ] Gate conditions are met
```

## 阶段门禁速查表

| 目标阶段 | 门禁条件 | 未通过时的操作 |
|----------|----------|---------------|
| 01 | RUNTIME_STATE: IDLE or 05(completed) | 先完成上一循环或重置状态 |
| 02 | TRUTH_AUDIT.md 存在 + RUNTIME_STATE: 01(completed) | 先完成 01 阶段 |
| 03 | CONSTITUTION.md + BUDGET.md 存在 + RUNTIME_STATE: 02(completed) | 先完成 02 阶段 |
| 04 | IMPLEMENTATION_PLAN.md 存在 + PR 已执行 + RUNTIME_STATE: 03(completed) | 先完成 03 和 PR |
| 05 | VERIFICATION_REPORT.md 存在 + VERDICT ≠ NON-COMPLIANT + RUNTIME_STATE: 04(completed) | 先完成 04 阶段 |

## BLOCKED 状态处理

当 `current_stage == BLOCKED` 时：

```markdown
# Architecture Cycle — BLOCKED

## Status

⚠️ **The Architecture Evolution pipeline is BLOCKED.**

**Block Reason**: {从 RUNTIME_STATE.json 读取的 block_reason}

## Required Action

Manual intervention is required. Possible actions:
1. Fix the inconsistency and reset RUNTIME_STATE.json to IDLE
2. Fix the root cause and re-run the failed stage
3. Review VERIFICATION_REPORT.md for compliance violations

## Resolution

After resolving:
1. Manually update RUNTIME_STATE.json: `{"current_stage": "IDLE", "active": false}`
2. Re-invoke `architecture-evolution/architecture-cycle`
```

## 禁止行为清单

- ❌ 不先调用 Runtime Controller 就推荐阶段
- ❌ 在 EXECUTION_ALLOWED=false 时仍推荐阶段
- ❌ 执行任何 Truth Audit / Constitution / Implementation / Verification / Sync 逻辑
- ❌ 修改任何文件（包括 RUNTIME_STATE.json）
- ❌ 创建 PR
- ❌ 混合多个阶段的建议
- ❌ 跳过阶段推荐
- ❌ 建议并行执行
- ❌ 在 BLOCKED 状态下建议任何阶段
