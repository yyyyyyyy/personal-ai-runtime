# Meaning Ontology · RFC v0.1

> 本文档定义 **Meaning World** 中的解释对象、它们各自回答什么问题、以及对象之间的引用与生成边界。
>
> 它不是 API 设计，也不是实现计划。`RUNTIME_SPEC.md` 冻结 7 Primitive；`HUMAN_RUNTIME_CONSTITUTION.md` 冻结权力结构；本文档冻结 **Meaning 层的本体分工**。
>
> 状态：**v0.1 — Experimental** ｜ 适配基线：backend v0.9.0 ｜ 实现见 `backend/app/experimental/`
>
> 依赖：[`HUMAN_RUNTIME_CONSTITUTION.md`](../HUMAN_RUNTIME_CONSTITUTION.md)（Draft）、[`EPISTEMIC_CLOSURE_RFC.md`](EPISTEMIC_CLOSURE_RFC.md) v0.1 Experimental
>
> 被引用：`TRAJECTORY_RFC.md`、`IDENTITY_RFC.md`

---

## Preamble

```text
Claims explain representations.
Trajectories explain continuity.
Beliefs explain recurrence.
```

**核心公理：**

```text
continuity ≠ recurrence
```

同一组人生素材可以同时支撑多条合法 Trajectory 与多条 Belief；事件相同、解释不同，是预期行为，不是数据错误。

---

## §0 — Scope

### §0.1 What This RFC Governs

Meaning World 管理 **对 Representation 的解释**，不管理：

- Reality（不可触及）
- State 投影的确定性重建（见 Closure / `verify_rebuild`）
- Commitment 与 Execution（Agency / Action 相位）

### §0.2 What This RFC Does Not Do

- 不新增 Runtime Primitive
- 不定义 Identity 叙事生成算法（见 `IDENTITY_RFC.md`）
- 不替代 `HUMAN_RUNTIME_CONSTITUTION.md` §4 Meaning Boundary 之 G1–G5 条文

---

## §1 — Three Interpretation Activities (M0.1)

Meaning World 中存在三种正交的解释活动：

| 对象 | 解释对象 | 问题 | 最小定义 |
|------|----------|------|----------|
| **Claim** | Representation | What does this mean? | local interpretation |
| **Trajectory** | Continuity | What remains continuous? | continuity interpretation |
| **Belief** | Recurrence | What repeats? | recurrence interpretation |

形式化：

```text
Claim       = local interpretation        （点）
Trajectory  = continuity interpretation   （线）
Belief      = recurrence interpretation   （面）
```

### §1.1 Claim

解释一个或少量表征的局部意义。

例：用户对某次对话的陈述、系统对某条 Observation 的点状推断。

### §1.2 Trajectory

解释一组事件是否构成 **同一条连续性**。

例：「2026 年创业冲动」相关事件是否属于同一条人生线。

> **Trajectory is not a stored fact.** Trajectory is a governed interpretation of cross-cycle continuity.  
> 详见 `TRAJECTORY_RFC.md` §0。

### §1.3 Belief

解释 **类似结构为何在不同时间重复出现**。

例：「用户周期性产生创业冲动」（2018、2026、2034 多次类似 episode）。

### §1.4 Orthogonality (M0.2)

```text
Trajectory explains continuity.
Belief explains recurrence.
```

| 维度 | Trajectory 问 | Belief 问 |
|------|---------------|-----------|
| 时间形态 | 这些事件是否同一条线？ | 为何类似 episode 会再现？ |
| 例 | 2026 想创业 → 调研 → 暂缓（一条线） | 2018 / 2026 / 2034 多次「想创业」（重复模式） |

**Trajectory ≠ 长一点的 Claim。**  
Claim 解释表征；Trajectory 解释连续性；Belief 解释重复性。三者时间尺度与问题域均不同。

---

## §2 — Two Independent Pipelines

Representation 进入 Meaning World 有两条 **独立管线**，不得混用：

### §2.1 Pipeline A — Recurrence (Belief Line)

```text
Representation
      ↓
   Pattern          （纯统计，无 LLM）
      ↓
   Belief           （recurrence interpretation）
```

**Pattern 是 Belief 的统计前驱，不是 Trajectory 的前驱。**

`Pattern` / `PatternDetected` 解释：「发生了什么规律」。  
`Belief` 解释：「为何这种规律值得作为重复性假说」。

### §2.2 Pipeline B — Continuity (Trajectory Line)

```text
Representation
      ↓
TrajectoryLinked     （边，可署名）
      ↓
Trajectory           （continuity interpretation）
```

`TrajectoryLinked` 解释：「这些事件是否属于同一连续性假说」。  
`Trajectory` 是 Trajectory Interpretation Space 中的条目，见 `TRAJECTORY_RFC.md`。

### §2.3 Pipeline Isolation (MUST)

```text
Pattern MUST NOT emit TrajectoryLinked.
Trajectory MUST NOT be derived from Pattern aggregation alone.
Belief MUST NOT substitute for Trajectory when answering continuity questions.
Trajectory MUST NOT substitute for Belief when answering recurrence questions.
```

---

## §3 — Interpretation Dependency DAG (M0.3)

Meaning 对象之间构成 **证据依赖有向无环图（Interpretation Dependency DAG）**，不是写入流水线。

```text
        Representation
         /          \
        ▼            ▼
     Claim      TrajectoryLinked
        \            /
         ▼          ▼
      (cite)    Trajectory
                    │
                    ▼ (cite)
        Pattern ──► Belief
```

### §3.1 Allowed: Downward Citation

高层解释 MAY 引用低层解释作为证据，不得越权生成低层对象：

```text
Trajectory MAY cite Claim(s), event_seq(s).
Belief     MAY cite Trajectory(s), Pattern(s), Claim(s).
```

### §3.2 Forbidden: Upward Generation

```text
Claim        MUST NOT emit TrajectoryLinked.
Trajectory   MUST NOT emit Belief.
Belief       MUST NOT emit TrajectoryLinked.
Pattern      MUST NOT emit TrajectoryLinked.
```

违反向上生成将形成解释闭环，导致 Meaning 层垄断叙述路径。

### §3.3 Independent Entry

以下路径合法，且不要求前置对象存在：

```text
TrajectoryLinked MAY be proposed without prior Claim.
Belief MAY be derived from Pattern without prior Trajectory.
Claim MAY exist without Trajectory or Belief.
```

---

## §4 — Cross-Reference Rules (M0.4)

### §4.1 Evidence Fields

引用 MUST 显式携带证据类型，禁止隐式织线或隐式归纳：

```text
Trajectory.evidence:  { claim_ids[], event_seqs[] }
Belief.evidence:      { trajectory_ids[], pattern_ids[], claim_ids[] }
```

### §4.2 Authority on Links

`TrajectoryLinked` 边 MUST 携带与 Meaning Boundary G1–G5 同构的署名元数据：

```text
TrajectoryLinked {
  event_seq
  trajectory_id
  actor
  confidence
  claim_status    // proposed | contested | ratified | released | rejected
}
```

一条 Event 可有多条 `TrajectoryLinked`；各边独立署名、独立争议。

### §4.3 Status Non-Inheritance

引用 proposed Trajectory 不得自动 ratify Belief。  
引用 ratified Belief 不得自动创建 TrajectoryLinked。  
各层署名独立。

---

## §5 — Relation to Constitution & Runtime Spec

| 上游文档 | 关系 |
|----------|------|
| `HUMAN_RUNTIME_CONSTITUTION.md` §2 | Observation / Self-Report / Claim 权力图谱；本 RFC 将 Claim 定位为 local interpretation |
| `HUMAN_RUNTIME_CONSTITUTION.md` §4 | Meaning Boundary G1–G5；本 RFC 不重复 G 条文，但 TrajectoryLinked 复用 `claim_status` |
| `RUNTIME_SPEC.md` | 7 Primitive 不变；Meaning 对象为投影与事件类型，非第 8 Primitive |
| `TRAJECTORY_RFC.md` | Trajectory 专论；引用本 RFC §1–§4 |

---

## §6 — Governance Pairing (Epistemic Stack)

Meaning Ontology 与三层治理对仗：

```text
Closure protects states.
Integrity protects competing continuity interpretations.
Identity preserves interpretive plurality.
```

| 世界 | 问题 | Meaning 对象 |
|------|------|----------------|
| State World | What exists now? | （非 Meaning；见 Closure） |
| Trajectory World | What has remained continuous? | Trajectory |
| Identity World | How are interpretations woven? | Projection over Trajectories + Beliefs |

Identity 不是 Meaning 存储对象。Identity Projection 可引用 Trajectory 与 Belief，但须保持 interpretive plurality（见 `IDENTITY_RFC.md`）。

---

## §7 — Ratification Checklist

以下条文 v0.1 拟冻结：

- [x] M0.1 — Claim / Trajectory / Belief 三分
- [x] M0.2 — `continuity ≠ recurrence`
- [x] M0.3 — Interpretation Dependency DAG
- [x] M0.4 — Cross-reference rules（cite down, no generate up）
- [x] §2 — Pattern → Belief 管线与 Trajectory 管线隔离

待后续 RFC 展开：

- [x] Identity Narrative Honesty（N1–N5）— 见 `IDENTITY_RFC.md`
- [x] `verify_meaning_dag.py`（CI 禁止向上生成）
- [x] Trajectory Registry schema（`TRAJECTORY_RFC.md` §1）

---

## §8 — Clarification (v0.1 Addendum, 2026-06)

### §8.1 Belief and Trajectory Are Orthogonal Pipelines

The Interpretation Dependency DAG (§3) is accurate w.r.t. **cite-down** rules, but
the implied layering (Trajectory → Pattern → Belief) does not reflect the actual
generation order. In the current implementation (`belief_engine.py`, `trajectory/engine.py`):

```text
Evidence (Representation)
├── Pattern Evidence  →  Belief    (explains recurrence)
└── Continuity Evidence → Trajectory (explains continuity)
```

Belief is generated from Pattern (statistical aggregation, no LLM), not from Trajectory.
Trajectory is generated from Continuity Evidence via TrajectoryLinked edges.
They are **parallel pipelines from Evidence**, not hierarchical layers.

The DAG remains valid for evidence citation (a Belief MAY cite a Trajectory as
evidence) but MUST NOT imply that Trajectory is a prerequisite for Belief generation.

### §8.2 Perspective as Interpretive Condition

Neither Belief nor Trajectory is a self-standing ontology primitive. Both are
**Perspective-bound interpretations**: the same Evidence, under different
Perspectives, can yield different Beliefs and different Trajectories.

Example:
- Evidence: "resigned from job, started freelancing"  
- Perspective `professional-growth` → Trajectory: "entrepreneurship arc"  
- Perspective `family-first` → Trajectory: "family absence arc"

Perspective itself is **not a Meaning Object** — it does not enter the Evidence DAG,
is not stored as a Claim, and is not governed by the epistemic state machine. It
belongs to the **Interpretive Layer** (above Ontology, below Projection), which is
not yet modeled in RUNTIME_SPEC or MEANING_ONTOLOGY. Future work may introduce an
`interpretive_frames.yaml` registry within the Interpretive Governance layer.

### §8.3 Tension as Claim Subtype

Tension (conflict between Belief and Behavior, competing Trajectories, etc.) is
modeled as a Claim subtype (`TensionProposed` event with `claim_type: "tension"`).
It reuses the existing epistemic state machine (proposed → contested → ratified
→ released) and `claim_authority.py` guards. No new Runtime Primitive is required.

---

## §9 — Amendment

变更本 RFC 之 MUST 语义须：

1. 说明影响 Trajectory RFC 或 Identity RFC 的哪一节
2. 不得隐式新增 Runtime Primitive
3. 若与 `HUMAN_RUNTIME_CONSTITUTION.md` 冲突，须先修宪

---

*Derived from: Recursive Epistemic Runtime / Temporal Epistemics design discussions, 2026-06.*
