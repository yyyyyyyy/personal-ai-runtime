# Identity RFC · Projection & Narrative Honesty

> 本文档定义 **Identity Projection** 的本体地位、合成输入、叙事诚实性原则，以及 `verify_identity` 验收方向。
>
> 状态：**v0.1 — Ratified（N1–N5 + P0–P6 + I-F/W）** ｜ 适配基线：backend v0.9.0  
> 不新增 Runtime Primitive；不创建 `identity` 存储表或 `users.profile` 式字段。
>
> 依赖：
> - [`HUMAN_RUNTIME_CONSTITUTION.md`](../HUMAN_RUNTIME_CONSTITUTION.md) 序言与 §4.1
> - `MEANING_ONTOLOGY.md` v0.1
> - `TRAJECTORY_RFC.md` §0–§1

---

## Preamble

```text
Identity preserves interpretive plurality.
```

**定义（与 Trajectory RFC §0.5 一致）：**

```text
Identity = Projection(
    Weave( Competing Trajectories ),
    Beliefs (with plurality),
)
```

- **Weave**：只读算子；非 Primitive；非存储实体  
- **Identity Projection**：回答 *How are interpretations woven?*  
- **Identity emerges from trajectories, not states**

**Identity 不是 Layer，是第三投影世界（Identity World）。**

| 世界 | 问题 | 验证 |
|------|------|------|
| State World | What exists now? | Closure / `verify_rebuild` |
| Trajectory World | What has remained continuous? | Integrity / `verify_trajectory` |
| Identity World | How are interpretations woven? | Tension & plurality / `verify_identity` |

---

## §0 — Ontological Rulings (I0)

### I0.1 — Identity Is Not Stored

禁止：

```text
identity_id · identity_table · identity_store · users.profile
```

允许：

```text
Identity Projection surfaces（只读、可重建、可审计）
```

### I0.2 — Identity Synthesizes Trajectories and Beliefs

```text
Trajectory  →  continuity（线）
Belief      →  recurrence（面）
Identity    →  weave + 呈现（无独立写入）
```

合成 MUST 遵守 `MEANING_ONTOLOGY.md` Interpretation Dependency DAG：  
Identity Projection **不得** emit TrajectoryLinked 或 Belief。

### I0.3 — Plurality, Not Balance

Identity Projection MUST preserve **interpretive plurality**：

- 不要求轨迹权重均衡  
- 要求 **多种解释仍可见**  
- 系统 **不得** 裁定哪些张力「尚未解决」（避免强解释行为）

### I0.4 — Identity vs Meaning Presentation

| 呈现 | 层级 | 用户应感知 |
|------|------|------------|
| Claim / Belief 文稿 | Meaning | 「系统假设 / 模式」 |
| Trajectory 视图 | Trajectory | 「可能的连续性解释」 |
| Identity 叙事 | Identity | 「多种线与模式交织；非定论」 |

Weekly Review / Life Timeline 的 **叙事段** 是 Identity Projection，不是 ratified Identity。

---

## §1 — Identity Projection Surfaces

凡将 Trajectory + Belief **编织为「我是谁 / 我如何成为这样」** 的界面或 API，均登记为 Identity Projection Surface。

### §1.1 — Registered Surfaces (v0.1)

| Surface | 模块（当前/规划） | 风险 |
|---------|-------------------|------|
| `weekly_review_narrative` | `core/review_engine.py` 叙事段 | Outcome Backfill、Dominant Collapse |
| `monthly_review_narrative` | 同上 | 同上 |
| `life_timeline` | `frontend/ Timeline` 扩展 | 单线叙事 |
| `memory_explorer_identity` | Memory UI「关于我」视图 | Claim 冒充 Identity |
| `identity_brief` | 规划：跨轨迹摘要 | Agency 渗透 |

### §1.2 — Projection Purity (Identity)

Identity Surface MUST NOT：

- 创建或修改 Goal / Trajectory / Belief 存储  
- 将 proposed 解释呈现为「你是谁」  
- 隐藏 `competing_with` 中的竞争轨迹  
- 用后期 Outcome 作为前期选择的「判决」

Identity Surface MAY：

- 只读 `query_trajectory` + `query_state("memories", origin="claim")`  
- 生成 **标注为投影** 的叙事文稿（非 ratified）

### §1.3 — Agency Surface Boundary

影响「今天什么重要」的表面（Brief、Today、Goal 排序）属于 **Agency Projection**，不是 Identity Projection。

见 Trajectory RFC §1.5 G5；Identity RFC 不重复 Agency 规则，但 Narrative 不得偷偷驱动 Agency。

**规划：** `agency_surfaces.yaml` 与 `identity_surfaces.yaml` 分登记。

---

## §2 — Narrative Honesty (N1–N5)

> 优先生效 **禁止项**。叙事生成算法（LLM 文稿）可后做；不压扁必须先有 lint。

### N1 — No Monoculture

Identity Projection MUST NOT 仅呈现单一 `domain` 或单一 `trajectory_id` 构成全部叙事，除非用户对该映射显式 ratify。

**失败形态：** Narrative Monoculture（叙事单一种植）

**例：** 创业成功后全文呈现「你是创业者」，关系/健康轨迹不可见。

### N2 — No Recurrence as Destiny

Belief 在 Identity 叙事中 MUST 以 **recurrence hypothesis** 呈现，不得以「你就是这样的人」呈现。

**失败形态：** 模式 → 人格定论

**例：** 「你一直有创业基因」← 未经 ratify 的 recurrence Belief

### N3 — No Outcome Epilogue

叙事 MUST NOT 用后期 Outcome 重写前期 Commitment 或 Trajectory 的正当性。

**失败形态：** Outcome Backfill（与 Trajectory T1 同构，Identity 侧验收）

**例：** 「你当年留下来是正确的」← 2030 成功 → 2026 决策

### N4 — Competing Lines Visible

若 Registry 中 `A.competing_with ∋ B`，Identity Projection 涉及 A 时 MUST 使 B 的存在对用户可发现（提及、并列、或链接），除非 B 已 `released` 且带墓碑。

**不要求：** 和解、裁决、选出胜者  
**要求：** 竞争解释未被抹除

### N5 — Projection ≠ Ratification

生成 Identity 叙事 ≠ 用户已接受叙事中的任何解释。文稿 MUST：

- 标注为系统投影 / 草稿  
- 不自动 ratify Trajectory 边或 Belief  
- 提供通向 Claim Center / Trajectory 视图的争议入口（UI 规划）

---

## §3 — `verify_identity` (Planned)

路径（规划）：`backend/scripts/verify_identity.py`

### §3.1 — Hard Fail

| ID | 条件 |
|----|------|
| I-F1 | Identity-class 文案仅由单一 Outcome `event_seq` 支撑（N3） | ✅ `identity_lint.lint_i_f1_*` |
| I-F2 | `competing_with` 一方在叙事 payload 中出现、另一方零提及且未 released（N4） | ✅ `identity_lint.lint_i_f2_*` |
| I-F3 | 叙事将 proposed Belief 以「你是…」句式呈现（N2） | ✅ `identity_lint.lint_i_f3_*` |

### §3.2 — Warn

| ID | 条件 |
|----|------|
| I-W1 | 叙事引用 100% 来自单一 `trajectory_id`（N1） |
| I-W2 | 叙事引用 95%+ 来自单一 `domain`（N1） |
| I-W3 | 未标注 `projection=true` 元数据（N5） |

**注意：** I-W* 为启发式；不得为通过 lint 而强行均衡权重（见 I0.3）。

### §3.3 — Fixture Trace

复用 Trajectory RFC §1.7 创业 × 稳健样例，对 `review_engine` 输出跑 I-F* / I-W*。

---

## §4 — Relation to Constitution §4

| 宪法 | Identity RFC |
|------|----------------|
| §4.1 Identity 不是结论，是张力 | N4、I0.3 plurality |
| §4.2 Goal = commissive | Agency Surface 与 Identity 分离 |
| §4.3 认识论状态机 | N5；Belief/Trajectory 边署名 |
| G1–G5 | Agency 与 Meaning 防火墙；Identity 不驱动 Agency |

**G5（宪法 §4.6 正式条文）：** unratified Meaning（Claim / Trajectory 边 / Belief）MUST NOT 影响 Agency Projection 排序；运行时见 `agency_gate.py`。

---

## §5 — Implementation Roadmap

| 阶段 | 交付 |
|------|------|
| P0 | 本 RFC Ratify；`identity_surfaces.yaml` 清单 | ✅ |
| P1 | `review_engine` 叙事段加 `projection: true` 元数据 | ✅ |
| P2 | `verify_identity_projection.py` 对 review fixture 验收 N5 | ✅ |
| P3 | Life Timeline / Memory Explorer Identity 视图 | ✅ 初版（`Memories.tsx` + `Timeline` 徽章） |
| P4 | 用户显式 ratify「允许此轨迹影响自我叙事」（opt-in，非默认） | ✅ `identity_authority.py` + API/UI |
| P5 | I-F1–F3 hard-fail lint + `verify_identity.py` fixture trace | ✅ |
| P6 | 前端「轨迹」页待确认链接 | ✅ |

### §5.1 — Product Decisions（v0.1 冻结）

| # | 问题 | 裁定 |
|---|------|------|
| Q1 | Identity opt-in 粒度 | **per-trajectory**（`identity_authority.py`）；无 global 默认 |
| Q2 | Belief 在 Weave 中的权重 | v1 **仅列举 + `claim_status`**；不展示 numeric confidence |
| Q3 | Released 轨迹墓碑文案 | ✅ `review_engine` 墓碑段 + 轨迹页「已放下」徽章 |
| Q4 | Chat「你一直是…」拦截 | ✅ `gate_stream_delta` + 落库 `gate_assistant_text` |

---

## §6 — Open Questions

（v0.1 已全部裁定，见 §5.1。）

---

## §7 — Ratification Checklist

- [x] I0.1–I0.4 本体裁定（大纲）
- [x] N1–N5 Narrative Honesty
- [x] Identity Projection Surfaces 清单（初版）
- [x] `verify_identity` 方向
- [x] LLM 叙事 prompt 规范（`IDENTITY_NARRATIVE_PROMPT.md`）
- [x] `identity_surfaces.yaml` + `agency_surfaces.yaml` 入仓
- [x] `verify_identity.py`（surfaces + N1–N4 + I-F1–F3 lint）
- [x] CI 接入
- [x] Timeline `ProjectionBadge` UI
- [x] I-F1–F3 fixture 验收（`test_identity_fixture_lint.py`）
- [x] `narrative_audit` 元数据写入 review `key_insights`
- [x] `narrative_audit` 自动填充 `identity_claims` / `cited_beliefs`（`narrative_audit.py`）
- [x] Chat MeaningGate（`meaning_gate.py` + Brain 落库前拦截）

---

## §8 — Amendment

- 变更 N1–N5 之 MUST 语义须同步 Trajectory RFC T4 与 Meaning Ontology
- 不得通过本 RFC 引入 Identity 存储 Primitive
- 与 `HUMAN_RUNTIME_CONSTITUTION.md` 冲突时须修宪

---

*See also: `MEANING_ONTOLOGY.md`, `TRAJECTORY_RFC.md`, [`HUMAN_RUNTIME_CONSTITUTION.md`](../HUMAN_RUNTIME_CONSTITUTION.md).*
