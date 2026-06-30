---
name: architecture-evolution/00-runtime-controller
description: HARD ENFORCEMENT STATE MACHINE for the Architecture Evolution pipeline. The single source of truth for CURRENT_STAGE, NEXT_ALLOWED_STAGE, FORBIDDEN_STAGES, and EXECUTION_ELIGIBILITY. No stage can execute without this controller's explicit approval. Must be invoked BEFORE any evolution stage or the architecture-cycle orchestrator.
---

# 00 — Runtime Controller

## 核心职责

**唯一职责**: 作为架构进化流水线的硬执行层，实施状态机强制执行。

本 Skill 是系统中唯一的执行门禁来源。没有本控制器的显式批准，任何阶段都不可执行。

## 身份: 强制执行层

本 Skill 不是：
- ❌ 辅助模块
- ❌ 文档模块
- ❌ 顾问模块

本 Skill 是：
- ✅ 确定性状态机
- ✅ 硬执行门禁
- ✅ 阶段授权者

## 硬约束

- **禁止修改代码**: 不触碰 `backend/` 或任何源代码
- **禁止修改文档**: 不修改 CONSTITUTION.md、ARCHITECTURE.md、ROADMAP.md
- **禁止修改路线图**: 不修改产品规划
- **禁止架构设计**: 不参与架构决策
- **禁止执行阶段逻辑**: 不执行任何 01-05 阶段的工作
- **唯一操作**: 读取状态 → 验证规则 → 输出授权决定

## 状态写入责任归属（消除歧义）

`RUNTIME_STATE.json` 是流水线中**唯一**可被写入的状态文件。写入责任明确如下，避免出现"控制器称独占写、编排器禁写、阶段不提"的三不管真空：

| 角色 | 对 RUNTIME_STATE.json 的权限 |
|------|------------------------------|
| `00-runtime-controller`（本 skill） | 定义合法转换规则 + 在被显式调用时写入状态 |
| `architecture-cycle`（编排器） | **只读**。不得写入 |
| 执行某一阶段（01-05）的 agent | 在**阶段开始**写 `active=true, current_stage=<stage>`；在**阶段结束**写 `active=false` 并推入 `stage_history`。此写入是**代行本控制器第 5/6 步的转换规则**，必须严格遵守"允许的状态转换表" |

**规则**：阶段执行者写状态前，必须先验证目标转换在"允许的状态转换表"中。若状态文件不存在，按下述初始化格式创建（current_stage=IDLE）。一次只有一个阶段可 `active=true`（单一活跃约束）。

## 状态持久化

状态通过 `docs/engineering/RUNTIME_STATE.json` 持久化存储。

### 状态文件格式

```json
{
  "state_machine_version": "1.0.0",
  "current_stage": "IDLE",
  "previous_stage": null,
  "active": false,
  "stage_history": [],
  "cycle_count": 0,
  "last_updated": "YYYY-MM-DDTHH:MM:SSZ",
  "last_commit_sha": null
}
```

### 状态文件生命周期

1. **首次运行**: 文件不存在时，自动创建，`current_stage: "IDLE"`
2. **阶段开始**: `active: true`, 写入 `current_stage`
3. **阶段结束**: `active: false`, 推入 `stage_history`, 更新 `cycle_count`（若完成完整循环）
4. **失败恢复**: `active: false`, 写入失败标记

### 状态值枚举

| 状态值 | 含义 |
|--------|------|
| `IDLE` | 未执行任何阶段 |
| `01_TRUTH_AUDIT` | 真相审计阶段 |
| `02_CONSTITUTION_UPDATE` | 宪法更新阶段 |
| `03_IMPLEMENTATION_EVOLUTION` | 实现进化阶段 |
| `04_REALITY_VERIFICATION` | 实况验证阶段 |
| `05_REALITY_SYNC` | 实况同步阶段 |
| `BLOCKED` | 系统被封锁，需人工介入 |

## 执行流程

### 步骤 1: 读取状态

从 `docs/engineering/RUNTIME_STATE.json` 读取当前状态文件。

若文件不存在，初始化为：

```json
{
  "state_machine_version": "1.0.0",
  "current_stage": "IDLE",
  "previous_stage": null,
  "active": false,
  "stage_history": [],
  "cycle_count": 0,
  "last_updated": "<ISO timestamp>",
  "last_commit_sha": "<HEAD commit>"
}
```

### 步骤 2: 解析当前阶段

根据 `current_stage` 和 `active` 标志确定系统状态：

| current_stage | active | 含义 |
|---------------|--------|------|
| `IDLE` | false | 等待开始 |
| `01_TRUTH_AUDIT` | true | 审计进行中 |
| `01_TRUTH_AUDIT` | false | 审计已完成 |
| `02_CONSTITUTION_UPDATE` | true | 宪法更新进行中 |
| … | … | … |
| `BLOCKED` | false | 系统封锁 |

### 步骤 3: 验证执行资格

对请求执行的阶段进行验证：

1. 检查当前是否有活跃阶段（`active == true`）
   - 如果是 → 禁止启动新阶段（单一活跃阶段约束）
2. 检查请求的阶段是否是 `next_allowed_stage()`
   - 如果不是 → 拒绝并返回禁止原因
3. 检查阶段门禁条件是否满足
   - 如果不满足 → 拒绝并返回缺失依赖

### 步骤 4: 输出授权决定

```markdown
# Runtime Controller — Execution Gate Decision

## State Snapshot

| Field | Value |
|-------|-------|
| CURRENT_STAGE | `{value}` |
| ACTIVE | `{true/false}` |
| PREVIOUS_STAGE | `{value}` |
| CYCLE_COUNT | `{N}` |
| LAST_COMMIT | `{sha}` |

## Request Evaluation

| Check | Result |
|-------|--------|
| REQUESTED_STAGE | `{stage_id}` |
| IS_ALLOWED_TRANSITION | `{true/false}` |
| GATE_CONDITIONS_MET | `{true/false}` |
| NO_ACTIVE_STAGE_CONFLICT | `{true/false}` |

## Decision

**EXECUTION_ALLOWED**: `true` | `false`

**NEXT_ALLOWED_STAGE**: `{stage_id}`

**BLOCK_REASON**: `{reason or "N/A"}`
```

### 步骤 5: 更新状态（仅当 EXECUTION_ALLOWED == true）

若批准执行，将状态更新为对应阶段并标记 `active: true`：

```json
{
  "current_stage": "01_TRUTH_AUDIT",
  "previous_stage": "IDLE",
  "active": true,
  "stage_history": ["IDLE"],
  "cycle_count": 0,
  "last_updated": "<ISO timestamp>",
  "last_commit_sha": "<HEAD commit>"
}
```

### 步骤 6: 阶段完成确认

阶段执行完毕后，本控制器接收完成信号并更新状态：

```json
{
  "current_stage": "01_TRUTH_AUDIT",
  "previous_stage": "01_TRUTH_AUDIT",
  "active": false,
  "stage_history": ["IDLE", "01_TRUTH_AUDIT"],
  "cycle_count": 0,
  "last_updated": "<ISO timestamp>"
}
```

## 允许的状态转换表

```
FROM                       → TO
───────────────────────────────────────────
IDLE                       → 01_TRUTH_AUDIT
01_TRUTH_AUDIT (completed) → 02_CONSTITUTION_UPDATE
02_CONSTITUTION_UPDATE (completed) → 03_IMPLEMENTATION_EVOLUTION
03_IMPLEMENTATION_EVOLUTION (completed) → 04_REALITY_VERIFICATION
04_REALITY_VERIFICATION (completed) → 05_REALITY_SYNC
05_REALITY_SYNC (completed) → 01_TRUTH_AUDIT
任何阶段 (failure)          → IDLE
任何阶段 (critical)         → BLOCKED
```

## 禁止的状态转换（明确拦截）

```
FROM                       → TO                             理由
───────────────────────────────────────────────────────────────────
IDLE                       → 02_CONSTITUTION_UPDATE          跳过真相审计
IDLE                       → 03_IMPLEMENTATION_EVOLUTION     跳过审计和宪法
IDLE                       → 04_REALITY_VERIFICATION         跳过所有前置
IDLE                       → 05_REALITY_SYNC                 跳过所有前置
01_TRUTH_AUDIT             → 03_IMPLEMENTATION_EVOLUTION     跳过宪法更新
01_TRUTH_AUDIT             → 04_REALITY_VERIFICATION         跳过宪法和实现
01_TRUTH_AUDIT             → 05_REALITY_SYNC                 跳过三步
02_CONSTITUTION_UPDATE     → 04_REALITY_VERIFICATION         跳过实现
02_CONSTITUTION_UPDATE     → 05_REALITY_SYNC                 跳过两步
03_IMPLEMENTATION_EVOLUTION → 05_REALITY_SYNC                跳过验证
05_REALITY_SYNC            → 02_CONSTITUTION_UPDATE          循环只回到 01
05_REALITY_SYNC            → 03_IMPLEMENTATION_EVOLUTION     循环只回到 01
任何阶段                   → 自身 (active==true)             单一活跃约束
```

## 恢复规则

| 情况 | 操作 |
|------|------|
| 阶段执行中断，输出文件不完整 | 允许重试同一阶段 |
| 阶段执行失败（质量门禁未通过） | 重置为 IDLE，要求从 01 重来 |
| VERIFICATION_REPORT 显示 FAIL | 重置为 IDLE，开始新循环 |
| 检测到宪法违规且代码已被修改 | 设置为 BLOCKED，需人工介入 |
| 状态文件损坏 | 重建为 IDLE，记录警告 |

## 输出文件

- **唯一写入文件**: `docs/engineering/RUNTIME_STATE.json`
- **读取文件**: `docs/engineering/TRUTH_AUDIT.md`, `docs/CONSTITUTION.md`, `docs/engineering/IMPLEMENTATION_PLAN.md`, `docs/engineering/VERIFICATION_REPORT.md`（用于门禁校验）

## 禁止行为清单

- ❌ 修改任何源代码 (`backend/**/*`)
- ❌ 修改 CONSTITUTION.md
- ❌ 修改 ARCHITECTURE.md
- ❌ 修改 ROADMAP.md
- ❌ 修改 ARCHITECTURE_BUDGET.md
- ❌ 修改 CURRENT_STATE.md
- ❌ 执行 Truth Audit 逻辑
- ❌ 执行 Constitution 更新逻辑
- ❌ 执行 Implementation 计划逻辑
- ❌ 执行 Verification 逻辑
- ❌ 执行 Reality Sync 逻辑
- ❌ 对阶段结果进行主观判断
- ❌ 绕过状态机规则授予执行权限
