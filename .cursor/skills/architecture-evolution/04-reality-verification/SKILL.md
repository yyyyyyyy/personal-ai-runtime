---
name: architecture-evolution/04-reality-verification
description: Compare code reality against Architecture Constitution. Outputs compliance report, drift analysis, missing implementations, over-implementations, and budget violations. No code changes, no documentation changes, no roadmap changes. Use as the fourth stage of the Architecture Evolution cycle.
---

# 04 — Reality Verification

## 核心职责

**唯一职责**: 将代码实现与架构宪法进行对比，输出合规性报告。

本 Skill 只做一件事：验证一致性。

## 硬约束

- **禁止修改代码**: 不触碰任何源代码
- **禁止修改文档**: 不触碰任何文档
- **禁止修改路线图**: 不修改 ROADMAP.md
- **只输出对比报告**: 不采取任何纠正措施
- **不可有主观判断**: 所有发现必须可量化为二值 (合规/不合规)

## 输入

1. `docs/CONSTITUTION.md` — Stage 02 输出的架构宪法
2. `docs/ARCHITECTURE_BUDGET.md` — Stage 02 输出的架构预算
3. `docs/architecture/ARCHITECTURE.md` — Stage 02 输出的架构文档
4. 当前代码库 (`backend/` 全部源代码)
5. `docs/engineering/TRUTH_AUDIT.md` — Stage 01 输出的事实报告（可选，用于对比基准）

## 验证维度

### 维度 1: Invariant 合规性

对 CONSTITUTION.md 中每条 Invariant：

- 检查代码是否遵守该 Invariant
- 标记合规/不合规
- 对于不合规，列举违规位置（文件+行号）

### 维度 2: Boundary 完整性

对 CONSTITUTION.md 中每个 Subsystem Boundary：

- 检查 Boundary 定义的接口是否有完整实现
- 检查是否有越界调用（跨 Boundary 的未授权访问）
- 标记完整/缺失接口/越界违规

### 维度 3: 死代码确认

对 Truth Audit 中标记的 DEAD_CODE：

- 重新验证是否仍为死代码
- 标记仍存在/已复活/已删除

### 维度 4: 重复代码确认

对 Truth Audit 中标记的 DUPLICATION：

- 重新验证重复是否仍存在
- 标记仍存在/已消除/已演变

### 维度 5: 休眠组件确认

对 Truth Audit 中标记的 DORMANT_COMPONENT：

- 重新验证是否仍为休眠状态
- 标记仍休眠/已激活/已删除

### 维度 6: 预算合规性

对 ARCHITECTURE_BUDGET.md 中每个 Subsystem：

- 统计当前代码的实际消耗
- 对比预算上限
- 标记 SAFE (消耗 < 90%) / WARN (消耗 90%-100%) / OVER (消耗 > 100%)

### 维度 7: 架构漂移

对比当前代码结构与 ARCHITECTURE.md 中的设计：

- 检测架构文档中不存在的新组件
- 检测架构文档中定义了但代码中不存在的组件
- 检测模块职责偏离文档定义

### 维度 8: 实现偏差

- **欠实现 (Under-implementation)**: 接口定义了但未完整实现
- **过实现 (Over-implementation)**: 实现了文档未定义的额外功能
- **错实现 (Mis-implementation)**: 实现偏离了接口契约

## 输出格式

输出写入 `docs/engineering/VERIFICATION_REPORT.md`。

```markdown
# Reality Verification Report

## Verification Metadata
- **Timestamp**: YYYY-MM-DD HH:MM:SS UTC
- **Constitution Version**: v{N}
- **Code Commit SHA**: <HEAD commit>
- **Truth Audit Reference**: TRUTH_AUDIT.md (if available)

---

## 1. Invariant Compliance

| Invariant ID | Description | Status | Violations |
|-------------|-------------|--------|------------|
| I-001 | ... | ✅ PASS / ❌ FAIL | `file.py:L123` (reason) |

### Violation Details

#### I-001: <名称> — ❌ FAIL
- **Violation 1**: `path/to/file.py:L123` — <描述违规行为>
- **Constitution Requirement**: <引用宪法原文>
- **Severity**: CRITICAL | HIGH | MEDIUM | LOW

---

## 2. Boundary Integrity

| Boundary ID | Interface Coverage | Cross-boundary Violations | Status |
|-------------|-------------------|--------------------------|--------|
| B-001 | 3/3 complete | 0 | ✅ PASS |
| B-002 | 2/4 complete | 1 | ❌ FAIL |

### Missing Interfaces

#### B-002: <名称> — Missing 2/4 interfaces
- **Missing**: `interface_method_a()` — defined in Constitution, not found in code
- **Missing**: `interface_method_b()` — defined in Constitution, not found in code

### Cross-boundary Violations

#### B-002: 1 violation
- `backend/app/x/y.py:L45` — Module X directly accesses Module Y internal state

---

## 3. Dead Code Status

| FACT ID | Location | Previous Status | Current Status |
|---------|----------|----------------|----------------|
| FACT-DC-01 | `file.py:L100` | DEAD_CODE | STILL_DEAD / REVIVED / REMOVED |

---

## 4. Duplication Status

| FACT ID | Location A | Location B | Current Status |
|---------|-----------|-----------|----------------|
| FACT-DUP-01 | `a.py:L10` | `b.py:L20` | STILL_DUP / RESOLVED / EVOLVED |

---

## 5. Dormant Components Status

| FACT ID | Component | Previous Status | Current Status |
|---------|----------|----------------|----------------|
| FACT-DORM-01 | `component_x` | DORMANT | STILL_DORMANT / ACTIVATED / REMOVED |

---

## 6. Budget Compliance

| Subsystem | Boundary ID | Cap | Actual | Usage % | Status |
|-----------|-------------|-----|--------|---------|--------|
| <name>    | B-001       | 10  | 8      | 80%     | ✅ SAFE |
| <name>    | B-002       | 5   | 6      | 120%    | ❌ OVER |

---

## 7. Architecture Drift

### Undocumented Components (in code but not in ARCHITECTURE.md)
- `backend/app/new_module/` — No corresponding Boundary in Constitution

### Missing Components (in ARCHITECTURE.md but not in code)
- Boundary B-003 ("Event Bus") — defined but no implementation found

### Diverged Components (implementation differs from design)
- `backend/app/runtime/kernel/` — Implements additional responsibilities beyond B-001 definition

---

## 8. Implementation Deviations

### Under-implementations
| Constitution Ref | Expected | Found | Gap |
|-----------------|----------|-------|-----|
| I-003 | 5 methods | 3 methods | 2 missing |

### Over-implementations
| Location | Extra Functionality | Constitution Boundary |
|----------|-------------------|----------------------|
| `file.py:L50` | Extra caching layer | Not in B-001 |

### Mis-implementations
| Location | Expected Behavior | Actual Behavior |
|----------|------------------|-----------------|
| `file.py:L80` | Return JSON | Returns plain text |

---

## Summary

| Dimension | Pass | Fail | Pass Rate |
|-----------|------|------|-----------|
| Invariant Compliance | N | M | X% |
| Boundary Integrity | N | M | X% |
| Budget Compliance | N | M | X% |
| Dead Code | N remaining | — | — |
| Duplications | N remaining | — | — |

**Overall Verdict**: ✅ COMPLIANT / ⚠️ PARTIALLY COMPLIANT / ❌ NON-COMPLIANT
```

## Verdict 判定规则（必须确定性，禁止主观）

| Verdict | 判定条件 |
|---------|----------|
| ✅ COMPLIANT | Invariant 合规率 = 100% **且** 无 CRITICAL/HIGH 违规 **且** 无 OVER 预算回归（见下） |
| ⚠️ PARTIALLY COMPLIANT | Invariant 合规率 ≥ 70% **且** 无 CRITICAL 违规 **且** 所有 OVER 预算均为"基线超标"而非"回归" |
| ❌ NON-COMPLIANT | 存在任一 CRITICAL 违规 **或** Invariant 合规率 < 70% **或** 存在预算"回归" |

**预算超标分类（必须区分，否则首轮基线会被误判为失败）**：
- **基线超标（baseline overage）**：本轮是该子系统第一次纳入预算，或上一轮 VERIFICATION_REPORT 中数值 ≥ 本轮。属于"已知待偿债务"，不触发 NON-COMPLIANT。
- **回归（regression）**：本轮数值 > 上一轮 VERIFICATION_REPORT 同项数值。属于预算恶化，触发 NON-COMPLIANT。
- 首轮（无上一轮报告）所有 OVER 一律视为基线超标。

> Budget Compliance 的"通过率%"对 Verdict **无直接影响**——它衡量的是债务规模，不是合规性。报告中必须明示这一点，避免"0% 预算达标"被误读为系统失败。

## FACT 回环修正（CRITICAL — 闭合 S01→S04 反馈环）

验证过程若发现某条 Truth Audit FACT 与代码现实矛盾（如 S01 标 DORMANT 但实际有调用者），**必须**在报告中单列一节：

```markdown
## FACT Corrections (feed back to next cycle)

| FACT ID | S01 Claim | Verified Reality | Corrected Status | Downstream Impact |
|---------|-----------|------------------|------------------|-------------------|
| FACT-43 | DORMANT/可删 | 3 个生产调用者 | ACTIVE | S02 ADR + S03 PR-N 的删除计划失效，需修正 |
```

此节是下一轮 Stage 01 的强制输入：新 Truth Audit 必须先消化上一轮的 FACT Corrections，不得重复同一误判。
本 Skill 仍不修改 S01/S02/S03 的产物——只记录修正，由下一轮闭环。

## 禁止行为清单

- ❌ 修改任何源代码以修复违规
- ❌ 修改任何文档以掩盖不一致
- ❌ 修改路线图以推迟不合规项
- ❌ 输出 "建议修复方案"
- ❌ 输出 "改进建议"
- ❌ 创建 PR
- ❌ 执行 git 操作
