# Interpretive Governance — Frame Layer Constitution

> 本文档治理的不是 Meaning World 中的对象（Claim / Belief / Trajectory），
> 而是**产生这些对象的解释框架（Interpretive Frame）从何而来、谁有权定义、如何消亡**。
>
> 状态：**v0.1 — Proposed**（尚未 Ratified；需长期运行验证）
>
> 依赖：`HUMAN_RUNTIME_CONSTITUTION.md` §1 · §4 · §7
> 关联：`MEANING_ONTOLOGY.md` §8.2 · `interpretive_frames.yaml`

---

## 序言

```text
Interpretation requires perspective.
Perspective diversity requires frame diversity.
Frame diversity requires that no single party defines all frames.
```

宪法规约 §1 保护的是「解释权」——任何人不得垄断对意义的解释。
本宪法规约保护的是「解释器定义权」——任何人不得垄断产生解释的条件。

前者保护的是 *what interpretations may exist*。
后者保护的是 *what interpretive lenses may exist to generate them*。

---

## §1 — Frame Authorship (F1–F3)

### F1 — User Frame Creation Right

**用户有权创建新的 Interpretive Frame。**
系统 MUST NOT 拒绝用户创建的 Frame（即使系统无法理解其语义），
仅可在 Frame 违反形式约束（如 ID 冲突）时退回并要求修正。

**实现：** Frame 创建走现有认识论状态机（Proposed → Ratified）。

### F2 — System Frame Proposal Limitation

系统 MAY 提议 Frame（`claim_status: proposed`），但 MUST NOT 成为 Frame 的唯一定义源。
在任何时候，用户创建的 Frame 数量不得少于系统预置的 Frame 数量。

### F3 — Frame Retirement with Tombstone

Frame 的废弃（Release）MUST 保留墓碑事件（`FrameReleased`），
记录「该 Frame 曾于 T 被定义，于 T' 被 Release」。
**释放的不是 Frame 的存在，而是 Frame 对当前解释的影响。**

---

## §2 — Frame Set Protection (F4–F6)

### F4 — No Singleton Frame Set

系统 MUST NOT 在任何时候将活跃 Frame 集收缩为单例。
`len(frames.filter(status=active)) >= 2` 必须始终成立。

### F5 — Frame Set Auditability

每次 Frame 集的变更（新增 / 废弃 / 修改）MUST 留下不可销毁的事件痕迹。
`FrameRegistered` · `FrameReleased` · `FrameRevised` 进入 Event Log。

### F6 — Default Frame Plurality

系统启动时预置的 Frame 数量不得少于 3，且必须覆盖至少 3 个不同的生活域
（career, relationship, health, wealth, creativity, etc.）。

---

## §3 — Relation to Epistemic State Machine

Frame 复用现有的认识论状态机，但不作为 Claim 存储：

| 状态 | 语义 |
|------|------|
| Proposed | Frame 被提议（系统或用户） |
| Ratified | Frame 被用户署名接受 |
| Contested | Frame 存在争议（未裁决） |
| Released | Frame 被废弃（墓碑保留） |

Frame 状态变更 MUST 经 `FrameRegistered` / `FrameRatified` / `FrameReleased` 事件。

---

## §4 — CI Enforcement (Planned)

路径（规划）：`backend/scripts/verify_interpretive_governance.py`

| ID | 条件 | 级别 |
|----|------|------|
| IG-F1 | Frame 集大小 < 2 | FAIL |
| IG-F2 | Frame 创建/废弃无对应 Event | FAIL |
| IG-F3 | 系统在 90 天内是唯一的 Frame 作者 | WARN |

---

## §5 — Amendment

- 变更 F1–F6 之 MUST 语义须同步审查 `HUMAN_RUNTIME_CONSTITUTION.md` §7
- 不得通过本宪法规约新增 Runtime Primitive
- Frame 作为治理配置，不属于 `RUNTIME_SPEC.md` 的 Primitive 冻结范围

---

## §6 — Open Questions (v0.1)

1. **Perspective 原子性的定义**：谁判定 `growth` 是一个有效原子维度而 `freedom_from_control` 不是？当前预设 Perspective 列表本身就是一种解释行为。
2. **Frame 冲突处理**：当两个 Frame 对同一 Evidence 产生互斥的 Trajectory 时，是并存还是通知用户裁决？
3. **Frame 创建门槛**：Frame 是否需要形式化验证（如至少包含 1 个 Perspective）？

这些问题属于 v0.1 的未决项。在积累足够的运行数据之前，不进入冻结范围。

---

*Derived from: Continuity Computing review discussions, 2026-06.*
