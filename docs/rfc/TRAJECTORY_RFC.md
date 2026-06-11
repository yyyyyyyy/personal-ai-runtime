# Trajectory RFC · §0 Ontological Rulings

> 本文档定义 **Trajectory** 在 Personal Reality Runtime 中的本体地位、与 Event 的关系、以及 **Integrity** 的保护对象。
>
> 状态：**v0.1 — Experimental（§0–§1 + P0–P7 实现）** ｜ 适配基线：backend v0.9.0  
> 实现见 `backend/app/experimental/`
>
> 依赖：`MEANING_ONTOLOGY.md` v0.1 Experimental、[`HUMAN_RUNTIME_CONSTITUTION.md`](../HUMAN_RUNTIME_CONSTITUTION.md)
> 关联：`IDENTITY_RFC.md`、`verify_trajectory` / `verify_trajectory_rebuild`

---

## Preamble

```text
Closure protects states.
Integrity protects competing continuity interpretations.
Identity preserves interpretive plurality.
```

**推导链（与宪法序言一致）：**

```text
Reality is recursive.
Reality is never stored. Only representations are.
Reality is layered.
…
Identity is woven.
Identity emerges from trajectories, not states.
```

---

## §0.1 — Two Worlds

Runtime 管理两个正交世界：

| 世界 | 问题 | 验证 | 性质 |
|------|------|------|------|
| **State World** | What exists now? | `verify_rebuild` → **Closure** | 确定性投影 |
| **Trajectory World** | What has remained continuous? | `verify_trajectory` → **Integrity** | 受治理的解释空间 |

```text
State World       = Projection World     （event → projector → state）
Trajectory World  = Interpretation World （events → continuity interpretation → trajectory）
```

Identity 不属于第三存储世界，而是 Trajectory World（及 Belief，见 Meaning Ontology）之上的 **只读投影**。见 §0.5。

---

## §0.2 — T0.1: Trajectory Is Interpretation, Not Fact

> **Trajectory is a governed interpretation of continuity, not a stored fact.**

Trajectory 属于 **Meaning World**，是 **continuity interpretation**（线），不是：

- Truth / Representation（见 `MEANING_ONTOLOGY.md` §0）
- Claim（点状 local interpretation）
- Belief（面状 recurrence interpretation）

```text
Claims explain representations.
Trajectories explain continuity.
```

详见 `MEANING_ONTOLOGY.md` §1。  
**continuity ≠ recurrence** — Trajectory 与 Belief 正交，不得相互替代。

同一组 Event 可支撑多条合法 Trajectory。事件相同、轨迹不同，是 **预期行为**，不是数据错误。

例：「我想辞职创业」可同时属于 `career-entrepreneurship`、`wealth-independence`、`identity-autonomy` 等连续性假说。

---

## §0.3 — T0.2: Event–Trajectory Is Many-to-Many

Event 与 Trajectory 的关系 MUST 为 **many-to-many**，通过 **TrajectoryLinked** 边表达。

### §0.3.1 Prohibition: Single-Value `topic_ref` on Events

禁止将 `topic_ref`（或等价单值字段）作为 Event 上的 **真值属性**。

单值字段暗示：

```text
系统已经知道该事件真正属于哪个主题
```

这与 Meta Principle 冲突：

```text
Reality is never stored. Only representations are.
```

`topic_ref` / `trajectory_id` 在 Registry 中是 **Trajectory Namespace**（连续性假说名），不是 Reality Namespace（客观范畴）。

### §0.3.2 TrajectoryLinked

边 MUST 携带署名元数据（与 Meaning Boundary G1–G5 同构，见 `MEANING_ONTOLOGY.md` §4.2）：

```text
TrajectoryLinked {
  event_seq
  trajectory_id
  actor
  confidence
  claim_status    // proposed | contested | ratified | released | rejected
}
```

`TrajectoryLinked` 声明的是：

```text
这些事件属于同一连续性解释
```

这是可争议的 Claim 类命题，作用在 **边** 上。一条 Event 可有多条边；各边独立署名。

### §0.3.3 Trajectory Registry

`trajectory_id` 在 Registry 中登记连续性假说，可含：

```text
id, domain, description, status,
competing_with[], parent
```

Registry 条目本身 SHOULD 可署名（proposed → ratified），不得静默创建竞争对而不经用户知晓。

---

## §0.4 — T0.3: Integrity Protects Competing Continuity Interpretations

**Integrity** 的对象不是任意单条 Trajectory，而是 **Trajectory Interpretation Space** —— 竞争性连续性解释合法并存的空间。

```text
Integrity preserves the legitimacy of competing continuity interpretations.
```

Trajectory Integrity Rules（T1–T4，§1 展开）统一保护：

| 规则 | 威胁 | 保护 |
|------|------|------|
| **T1** | Outcome Backfill | 结果不得 retroactively 改写过往连续性叙事 |
| **T2** | Tension Collapse | 竞争 Trajectory 之间的张力须保留 |
| **T3** | Outcome-authored Claims | 自 Outcome 生成的 Claim 须标注 evidence_type=outcome |
| **T4** | Dominant Trajectory Collapse | Identity 叙事不得坍缩为单一 Trajectory |

`verify_trajectory` 验证 **图完整性与张力的合法性**，不裁决哪条 Trajectory「正确」。

**Closure protects states. Integrity protects competing continuity interpretations.**

---

## §0.5 — T0.4: Identity Is Projection, Not Object

> **Identity is a projection of woven competing trajectories, not a stored object.**

```text
Identity = Projection(
    Weave( Competing Trajectories ),
    Beliefs (with plurality),    // 见 MEANING_ONTOLOGY.md；Identity RFC 展开
)
```

- **Weave**：只读算子，非 Primitive，非存储表
- **Identity Projection**：回答 *How are interpretations woven?*
- **Identity preserves interpretive plurality**：多种解释须仍可见；系统不得裁定哪些张力「尚未解决」

禁止：

```text
identity_id / identity_table / identity_store / users.profile 式 Identity 字段
```

否则退化为可写入的人格标签。

**Identity emerges from trajectories, not states.**  
Emergent 是性质；Trajectory 是连续性结构；Woven 是多轨交织 —— 见宪法序言。

---

## §0.6 — Relation to Frozen Primitives

本 RFC **不新增** Runtime Primitive。

| 写入 | 读出 |
|------|------|
| `emit_event`：`TrajectoryLinked`, `TrajectoryRegistered`, … | `query_trajectory`（§1 定义，virtual 或 materialized） |
| `event_log` 为唯一真相源 | Trajectory 图为 governed read aggregate |

`correlation_id`（单次意图 trace）与 `trajectory_id`（跨 Cycle 主题线）**语义不同**，不得混用。见 `RUNTIME_SPEC.md` Event schema；`trajectory_id` 仅出现在 TrajectoryLinked / Registry，不作为 Event 单值真值字段。

---

## §0.7 — Epistemic Cycle Context

Trajectory 位于 Recursive Epistemic Cycle 的 Meaning 相位（连续性解释），不是 Cycle 的终点：

```text
observe → interpret → commit → execute → re-observe (Outcome as new Representation)
                ↑
         Trajectory Interpretation Space
```

Outcome 作为 world-authored Representation 重新进入循环；T1 防止 Outcome 污染过往 Trajectory Interpretation Space。

---

## §0.8 — §0 Ratification Summary

| 裁定 | 状态 |
|------|------|
| T0.1 Trajectory is interpretation, not fact | Draft for Ratify |
| T0.2 Event–Trajectory many-to-many via TrajectoryLinked | Draft for Ratify |
| T0.3 Integrity protects competing continuity interpretations | Draft for Ratify |
| T0.4 Identity is projection, not object | Draft for Ratify |
| Preamble 三句 | Draft for Ratify |

### §0.8.1 Implications Once Ratified

- 单值 `event.topic_ref` 模型 **出局**
- `TrajectoryLinked` + Trajectory Registry **入局**
- `verify_trajectory` 验证 **图与张力**，非字段一致性
- `verify_identity` 验证 **interpretive plurality**（Identity RFC）
- Belief ↔ Trajectory 分工以 `MEANING_ONTOLOGY.md` 为准，不在本 RFC 重复

---

## §1 — Registry, Events, and Integrity Rules

> §1 定义 §0 裁定的工程落点。不新增 Runtime Primitive；所有写入经 `emit_event`。

### §1.1 — Trajectory Registry

Registry 存放 **连续性假说**（Trajectory Namespace），不是 Reality 分类。

**位置（Phase 1）：** `backend/trajectory_registry.yaml`（治理配置，可版本化）  
**位置（Phase 2，可选）：** `TrajectoryRegistered` 事件 + 投影表 `trajectory_registry`

#### §1.1.1 Schema

```yaml
# trajectory_registry.yaml
version: 1
trajectories:
  - id: career-entrepreneurship-2026
    domain: career
    description: "Career decisions related to entrepreneurship impulse (2026 arc)"
    status: active          # active | dormant | released
    claim_status: proposed  # proposed | contested | ratified | released | rejected
    parent: career
    competing_with:
      - career-corporate-stability-2026

  - id: career-corporate-stability-2026
    domain: career
    description: "Staying in corporate role while evaluating alternatives"
    status: active
    claim_status: proposed
    parent: career
    competing_with:
      - career-entrepreneurship-2026
```

| 字段 | MUST | 说明 |
|------|------|------|
| `id` | ✅ | 全局唯一 Trajectory ID；禁止与 `correlation_id` 混用 |
| `domain` | ✅ | 粗域（career / health / relationship / wealth / …）；供 Identity plurality lint |
| `description` | ✅ | 人类可读的连续性假说描述 |
| `status` | ✅ | 轨迹是否仍活跃呈现 |
| `claim_status` | ✅ | Registry 条目本身可署名；竞争对不得静默创建 |
| `competing_with` | 推荐 | 张力对；T2 / verify_trajectory 检查其双向存在 |
| `parent` | 可选 | 层级命名空间（如 `career`） |

#### §1.1.2 Registry Rules

```text
R1  新建 competing_with 对 MUST emit TrajectoryRegistered 或用户显式 ratify
R2  禁止仅 UI/LLM 内存持有竞争关系而不入 Registry 或 Event
R3  released 轨迹保留墓碑；不得 DELETE Registry 行而不留 Event
```

---

### §1.2 — Event Types

所有 Trajectory 写入 MUST 经 Kernel `emit_event`。建议事件类型：

#### §1.2.1 `TrajectoryRegistered`

登记或更新 Registry 中的连续性假说。

```text
Event {
  type:             TrajectoryRegistered
  aggregate_type:   trajectory
  aggregate_id:     <trajectory_id>
  actor:            user | system | kernel
  payload: {
    domain:           string
    description:      string
    parent:           string | null
    competing_with:   string[]
    claim_status:     proposed | …
  }
}
```

#### §1.2.2 `TrajectoryLinked`

将已有 Event（按 `event_seq`）链接到 Trajectory。**边事件，非 Event 单值字段。**

```text
Event {
  type:             TrajectoryLinked
  aggregate_type:   trajectory
  aggregate_id:     <trajectory_id>
  actor:            user | system | kernel
  payload: {
    event_seq:        int          # 目标 event_log.seq
    link_id:          string       # 边唯一 id（用于 ratify/release 边）
    confidence:       float        # 0.0–1.0
    claim_status:     proposed | contested | ratified | released | rejected
    rationale:        string | null  # 可选；系统链接时 SHOULD 提供
  }
  caused_by:        <prior TrajectoryLinked or source event id>  # 推荐
}
```

**MUST NOT：** 在任意 Event 的 payload 根上设置单值 `topic_ref` 作为真值。

#### §1.2.3 `TrajectoryLinkRatified` / `TrajectoryLinkRejected` / …

边级署名状态变迁。MUST 复用 Meaning Boundary 认识论状态机（与 `ClaimRatified` 同构）。

实现选项 A（推荐）：复用 `ClaimRatified` 等，令 `aggregate_type=trajectory_link`，`aggregate_id=link_id`。  
实现选项 B：独立事件类型 `TrajectoryLinkRatified`，projector 写入边投影。

#### §1.2.4 `correlation_id` vs `trajectory_id`

| 字段 | 尺度 | 用途 |
|------|------|------|
| `correlation_id` | 单次意图 / 单次 Cycle | trace 调试、Task 链 |
| `trajectory_id` | 跨 Cycle 人生主题 | TrajectoryLinked / Registry |

同一创业弧线可有多个 `correlation_id`、一个 `trajectory_id`。

---

### §1.3 — Read Surface: `query_trajectory`

不新增 Frozen Primitive；作为 **Read ABI 扩展** 须单独 RFC 注记（本 RFC 授权 Trajectory 只读面）。

#### §1.3.1 Phase 1 — Virtual（推荐首发）

```text
query_trajectory(trajectory_id) → {
  registry:   { ... },           # 来自 YAML 或 TrajectoryRegistered 投影
  links:      [ TrajectoryLink ], # event_log 中 TrajectoryLinked 重放
  events:     [ Event ],          # 按 event_seq 拉取
  competing:  [ trajectory_id ],  # 来自 registry.competing_with
}
```

由 `event_log` 现场编织；无额外 governed 表。

#### §1.3.2 Phase 2 — Materialized（可选）

表 `trajectory_links`（APP_STORAGE 或 governed 只读投影）由 `TrajectoryLinked` projector 维护；`verify_rebuild` 扩展或独立 `verify_trajectory_rebuild`。

---

### §1.4 — Trajectory Integrity Rules (T1–T4)

可执行条文；`verify_trajectory.py` 验收对象。

#### T1 — No Outcome May Rewrite History

Outcome（world-authored Representation，post-Execution）MUST NOT：

- 自动降低过往 `TrajectoryLinked` 的 `claim_status` 权重
- 在 Narrative / Brief 中将后期 Outcome 表述为对前期 Commitment 的「证明」
- 删除或覆盖竞争 Trajectory 的 Registry 条目

Outcome 可触发 **新的** `TrajectoryLinked` 与 proposed Claim；不得 retroactively 编辑既有边。

#### T2 — Trajectory Preserves Tension

对 Registry 中 `A.competing_with ∋ B`：

- 呈现 Trajectory A 时 MUST 可发现 B 仍存在（或已 released 带墓碑）
- 禁止仅呈现「胜出的」一条而静默另一条（除非用户 Release）

#### T3 — Outcome-Authored Claims

自 Outcome 派生的 Claim / Belief MUST：

```text
payload.evidence_type = "outcome"
claim_status = proposed   # 默认
```

且 MUST NOT 单独作为 T4 Identity 叙事的唯一证据。

#### T4 — Cross-Reference to Identity RFC

单 Trajectory 不得独占 Identity Projection（详见 `IDENTITY_RFC.md` N1、N4）。  
Trajectory RFC 的 `verify_trajectory` 不验收 Identity 合成；仅验收图与张力的 Integrity。

---

### §1.5 — Integration with `claim_authority`

`TrajectoryLinked` 与 Registry 条目的 `claim_status` SHOULD 复用 `claim_authority.py` 语义：

| 能力 | Trajectory 边 | Memory Claim |
|------|---------------|--------------|
| `can_present` | 边 + Registry | memory row |
| `can_drive_agency` | 默认 **false**（G5） | ratified only |
| `ratify` / `reject` / … | 边 id 或 trajectory aggregate | memory id |

**G5（Meaning → Agency）：** proposed Trajectory 或 proposed 边 MUST NOT 影响 Goal 排序、Brief Top N、Today 排名。见 `IDENTITY_RFC.md` Agency Surfaces。

---

### §1.6 — `verify_trajectory` Acceptance

脚本路径（规划）：`backend/scripts/verify_trajectory.py`

| 检查 | 级别 | 说明 |
|------|------|------|
| V1 | FAIL | `competing_with` 双向不一致 |
| V2 | FAIL | `TrajectoryLinked` 指向不存在的 `event_seq` |
| V3 | FAIL | Outcome 事件后自动 ratify 竞争边（T1） |
| V4 | WARN | 竞争对中一方零链接、另一方有多链接且未 released |
| V5 | WARN | Registry 条目 `claim_status=proposed` 但被 Identity 叙事引用 |

CI：Phase 1 可与 `make test` 并列；初期可用 fixture DB + 创业冲动样例。

---

### §1.7 — End-to-End Acceptance Trace（创业 × 稳健）

**Given** Registry 含 `career-entrepreneurship-2026` ↔ `career-corporate-stability-2026`

| Step | Event / Action | 验收 |
|------|----------------|------|
| 1 | User SelfReport → event seq=100 | — |
| 2 | `TrajectoryLinked`(100 → entrepreneurship), proposed | 边存在 |
| 3 | `TrajectoryLinked`(100 → corporate-stability), proposed | 多边合法 |
| 4 | 6× ConversationRecorded（同 trajectory，不同 correlation_id） | 链可 `query_trajectory` |
| 5 | Goal「暂缓离职」commitment | Agency；不 ratify 轨迹 |
| 6 | 2030 Outcome Observation seq=500 | 新 Representation |
| 7 | 系统 proposed Belief「适合冒险」 | T3；不 T1 改写 2026 边 |
| 8 | Identity Projection 草稿 | 竞争两条线均可见（Identity RFC） |

---

## §2 — Implementation Roadmap

| 阶段 | 交付 | 状态 |
|------|------|------|
| P0 | `trajectory_registry.yaml` + 文档 | ✅ |
| P1 | `TrajectoryLinked` / `TrajectoryRegistered` emit + virtual `query_trajectory` | ✅ `app/core/runtime/trajectory/` |
| P2 | `link_authority` + `/api/trajectories` | ✅ 初版 |
| P3 | `verify_trajectory.py` + `make trajectory-verify` | ✅ |
| P4 | Materialized `trajectory_links` + `verify_trajectory_rebuild.py` | ✅ |
| P5 | CI 接入 `.github/workflows/ci.yml` | ✅ |
| P6 | `ConversationRecorded` + Brain 自动 `TrajectoryLinked` 提议 | ✅ `conversation_recorder.py` |
| P7 | 前端「轨迹」页 + `/pending-links` 署名 UI | ✅ `frontend/src/pages/Trajectories.tsx` |

---

## §3 — Amendment

- §0 之 MUST 语义变更须同步审查 `MEANING_ONTOLOGY.md` 与 Identity RFC
- 不得通过本 RFC 新增 Runtime Primitive
- 若需修改 `RUNTIME_SPEC.md` Event schema 之 MUST 语义，须单独 RFC

---

*See also: `MEANING_ONTOLOGY.md`, [`HUMAN_RUNTIME_CONSTITUTION.md`](../HUMAN_RUNTIME_CONSTITUTION.md), [`RUNTIME_SPEC.md`](../RUNTIME_SPEC.md).*
