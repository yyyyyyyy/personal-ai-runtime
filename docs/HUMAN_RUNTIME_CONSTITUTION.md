# Human Runtime · 宪法（CONSTITUTION）

> 这份文档不是设计，也不是实现计划。`RUNTIME_SPEC.md` 回答「系统**怎么工作**」；这份文档回答它**上面**的一层：
> **「系统为谁而做，以及永远不能对人做什么。」**
>
> 它记录的不是 Primitive、不是 API、不是架构，而是 **哪些权力永远不允许被系统、模型、Agent、甚至未来的开发者拿走**。
> 它绑住的首要对象，是未来那个会因为「实现方便」而想悄悄挪动权力的人——很可能就是未来的我们自己。
>
> 状态：**v1.0 — Draft（实验性治理参考）** ｜ 位于 `RUNTIME_SPEC.md` 之上 ｜ 适配基线：backend v0.9.0
>
> **底座聚焦（2026-06）：** 修宪流程暂停。本文档与 Meaning 层 RFC 为设计参考；Meaning 相关实现已迁入 `experimental/`，待真实用户验证后再决定是否重新冻结。

---

## 序言 — Preamble（Epistemic Stack）

> 本节冻结 **Personal Reality Runtime** 的认识论公理与治理对仗。  
> 详细展开见：`rfc/MEANING_ONTOLOGY.md`、`rfc/TRAJECTORY_RFC.md`、`rfc/IDENTITY_RFC.md`。

### 公理（Axioms）

```text
Reality is recursive.
Reality is never stored. Only representations are.
Reality is layered.
```

### 相位治理（Cycle Phase Governance）

```text
Experiences are Data.        （表征如何进入循环）
Meaning is Negotiated.       （解释如何产生与署名）
Agency is Commissive.        （承诺如何绑定未来）
Action is Governed.          （执行如何作用于世界）
```

### 时间与身份（Temporal & Identity）

```text
Identity is Trajectory.      （单维：连续性从哪来）
Identity is Woven.           （多维：多条轨迹的交织）
Identity emerges from trajectories, not states.  （不可写入）
```

**核心句：** *Reality is recursive; identity is woven.*

### 治理对仗（Governance Pairing）

```text
Closure protects states.
Integrity protects competing continuity interpretations.
Identity preserves interpretive plurality.
```

| 世界 | 问题 |
|------|------|
| State World | What exists now? |
| Trajectory World | What has remained continuous? |
| Identity World | How are interpretations woven? |

Meaning World 三分（见 Meaning Ontology RFC）：Claim（点）· Trajectory（线）· Belief（面）；`continuity ≠ recurrence`。

---

## §0 — 北极星：保存连续性，而不集中权力

> **Human Runtime is a system for preserving continuity without concentrating authority.**
>
> **Human Runtime 是一个在不集中权力的前提下，保存连续性的系统。**

它不是保存「你是谁」的系统，而是保存「**你如何持续成为你自己**」的系统。
前者需要答案；后者允许问题长期存在。能活十年的，是后者。

它由两根支柱构成，缺一不可：

```text
连续性（Continuity）   ←  Immutable Experience Store     缺它 → 一纸政治宣言
权力制衡（Balance）    ←  四条边界（§3）                 缺它 → 一座数字档案馆
两者一起                                                  →  数字自我（Digital Self）
```

模型是访客，运行时是房子。模型可换（DeepSeek → 任何一代）；个人的经验底座不可换——它是唯一会随时间复利、且无法被复制的资产。**护城河不是「我们更懂你」（那是必输的赌），而是「这份自我底座归你所有、跨模型永续」。**

---

## §1 — 第一性原理：敌人是垄断，不是系统

很多人以为 Human Runtime 的危险是「系统获得了定义你的权力」。这只说对了一半。

> **真正的敌人是垄断——无论垄断者是系统，还是用户本人。**

- 系统独揽解释权 → **法官 / 人格管理器**（替你裁决你是谁）。
- 用户独揽解释权 → **谄媚镜子**（永远同意你，让你停止理解自己）。

这两者不是对立，是同构——只是换了个统治者。镜子也是囚笼，只是更舒服。

> **宪法铁律（First Principle）：任何单一一方（系统 / 用户 / 模型 / Agent / 开发者）都不得对「意义」握有全部权力。**

「数字自我 vs 数字人格管理器」的分界线，精确地说不是「谁握有解释权」，而是 **是否有任何一方握有了全部解释权**。

---

## §2 — Authority Graph：对象之下的真正结构

对象（Observation / Self-Report / Claim）真正的区别，**不是数据类型，而是谁拥有否决权**。对象模型之下的承重结构，是一张权力图谱：

| 层 | 是什么 | 作者 | 否决权归属 | 可变性 |
|----|--------|------|-----------|--------|
| **Observation** | 世界发生的事实 | 世界 / 连接器 | **无人拥有** | 内容可 Release（带墓碑），结构永不可篡改 |
| **Self-Report** | 用户对自身的陈述（证词） | 用户 | **仅作者（用户）** | 不可被系统覆盖；用户可 Revise / Retire |
| **Claim** | 系统的推断（假设） | 系统 | 作者可 Revise；用户可拒绝赋予**行动权**；新证据可挑战 | 可重推导的投影，永不是 Source of Truth |

**关键不对称：** 否决权的分配本身，就是宪法。`Observation` 谁都不能否决（否则退化成记忆美容）；`Self-Report` 只有用户能否决（这是你自己的言说）；`Claim` 的否决权被**三方分割**——这正是 §1 反垄断原则在对象层的落点。

> Substrate 的不变量不是「内容为真」，而是 **「在 seq=N、由 actor=X、于 T，这件事被记录过」——这个记录行为本身永远为真**。因此自陈（actor=user）与系统推断的生命周期事件（actor=system）都进入同一个不可变 Experience Store，只是作者不同。世界事件与自陈之间的**落差**（系统记录你没回信 / 你自陈我回了），正是自我欺骗的藏身处，也是 Human Runtime 能照见、而大模型照不见的东西——前提是永不把两者混成一类。

---

## §3 — 四条边界：它们都在约束「权力如何流动」

| 边界 | 禁止什么 | MUST | 执行 |
|------|---------|------|------|
| **Truth（Event Sourcing）** | 禁止修改过去 | 凡改变系统者必 emit 不可变 Event；State/Memory/Claim 皆为投影，可重建 | `verify_rebuild.py` |
| **Action（Governance）** | 禁止越权行动 | 一切对世界的作用必经 `invoke_capability` + Approval | `check_boundary.py` |
| **Data（Egress）** | 禁止越权传播 | 任何离开本机的数据必经 Egress 裁决并留痕 | `egress_gate.py` · `verify_egress.py`（LLM v0.1） |
| **Meaning** | 禁止垄断解释 | 见 §4 | `verify_meaning_boundary.py` · `verify_claim_authority.py` |

前三条已在 `RUNTIME_SPEC` / 路线图中。**Meaning Boundary 是这场对话新产出的第四条，也是 Human Runtime 区别于 AI Runtime 的那条。**

---

## §4 — Meaning Boundary（意义边界）

意义边界有**对称的两个职责**，缺任一个都会塌成一种失败形态：

```text
对上（意义层）：保全未和解的张力，禁止把未解之事压成一个答案。
对下（行动层）：支持人在张力未解时形成临时承诺，
                禁止让该承诺冒充为张力的「和解」。
```

### 4.1 Identity 不是对象，是持续协商

人核心的矛盾——事业↔家庭、自由↔稳定、控制↔信任、独立↔归属——可能十年没有最终答案。**值得保存的不是「最后选了哪边」，而是「这个人如何与这些矛盾长期共处」。** 因此：

> Identity 不是结论，而是一组长期未解决的解释张力。系统无权把它压扁成一个答案。

### 4.2 Goal 是「本轮选择」，不是意义的终点

人不为被理解而活，为行动而活。一个只会呈现张力、永不帮人动一步的系统，是**档案管理员**（第三种失败，见 4.5）。解法：把 `Goal` 钉在正确的位置——

```text
Goal / Intent = commissive（承诺），不是 claim（断言）
              = 「Meaning 尚未解决时，行动层的一次局部冻结 / 本轮选择」
              = 可撤销、不声称解决任何根本矛盾
禁止：把「今晚我选择加班」calcify 成「我已确定事业 > 家庭」
```

人真实的活法，就是**在根本性的不确定中果断行动**。这是 Meaning Boundary 与 Governance 的连接点。

### 4.3 Representation ≠ Authority · 认识论状态机

`Proposed / Contested / Ratified / Rejected / Revised / Released` 不是工作流，是**认识论状态**。

```text
Proposed   系统提出的假设
Contested  用户与证据分歧，并存，不裁决
Ratified   用户署名认可
Rejected   用户不接受 —— 是 Dormant（休眠），不是终态
Revised    被新理解修订（旧版本作为历史保留）
Released   影响被解除（墓碑长存，见 §5）
```

> **Reject 切断的是 Authority（行动权），不是 Representation（呈现权）。** 一次 Reject 不得授予用户「永久沉默权」——否则谄媚镜子从后门溜回。**新证据可令 `Rejected → Contested`**（"你两年前否决了这条；此后又多了 5 个数据点"）。解释权不能被垄断——这条原则**同时约束系统和用户**。

### 4.4 行动权映射

| 状态 | 可驱动 Action | 可呈现 |
|------|--------------|--------|
| Ratified | ✅ | ✅ |
| Contested | ❌ | ✅ |
| Rejected (Dormant) | ❌ | 仅在**实质性新证据**下可重新呈现（→ Contested） |
| Proposed | ❌（未署名前） | ✅（作为「系统假设」，绝不以「你是谁」呈现） |

### 4.5 三个失败极 · 可证伪测试

```text
法官  ：把未解之事压成裁决            → 越权（违 §1）
镜子  ：永远同意你 / Reject 即永久消音 → 谄媚（违 4.3）
档案员：完美保全张力，却永不帮你行动   → 瘫痪（违 4.2）

第一刀证伪切片（对齐 RUNTIME_SPEC §4 的精神）：
能否把一个你背了多年的张力——连同证据、对立解释、你历年移动过的立场、
你的修订与放下——原样呈现给你，
  ① 不压成裁决   ② 不沉默回避   ③ 同时还能帮你今天做出临时承诺
三者同时做到 = 真的 Human Runtime；缺任一 = 退化为上面某一极。
```

### 4.6 执行守卫（`check_meaning_boundary`）

宪法不是诗。Meaning Boundary 必须可被 CI 否决，与 Kernel Boundary 平级：

```text
G1  任何 high-stakes 的 system Claim，未 Ratified，不得出现在驱动 Agency 的因果链上
    → Action 的 caused_by 回溯到未署名的 Identity-class Claim ⇒ 构建失败
G2  投影冲突时 Self-Report(actor=user) 压过 Claim(actor=system)
    → 系统推断永以「系统假设」呈现，绝不以「你是谁」呈现
G3  任何呈现给用户的 Identity-class Claim 必须可证伪：
    无 evidence 边、或不暴露 Reject/Revise/Release ABI ⇒ 违宪（可 lint）
G4  任何 Influence 必须可 Release；存在不可解除的影响 ⇒ 违宪
G5  unratified Meaning（Claim / Trajectory 边 / Belief）MUST NOT 影响 Agency Projection 排序
    → Brief、Today、Goal 排名仅可由 commissive Goal 字段 + ratified Meaning 微调驱动
    → `agency_gate.py` · `verify_agency_surfaces.py`
```

> 未决硬边（留给实现，不影响冻结）：**谁判定一个 Claim 是否 high-stakes？** 系统判 → 可把自利 Claim 标为低风险绕过署名；全交用户判 → 同意疲劳。这是 §8 之下的问题，但 G1 的存在使它**必须**被回答。

---

## §5 — 遗忘 / Release：放下，而非篡改

人没有「重写历史」的权利，但有「停止被历史支配」的权利。所以遗忘是 **Release / Retire / Absolve**，不是 Delete——「这件事不再定义我」，而非「这件事从未发生」。

```text
永远不可侵犯：结构墓碑——「seq=N 处曾有记录，于 T 被用户 Release」
可被处置：内容——Mute（可逆遮蔽）或 Shred（不可逆销毁，crypto-shredding）
```

> **不可变约束的是结构，不是内容。** 防「理想化自我」的防线不是「内容不可删」，而是「**墓碑不可删**」——疤还在，所以你无法把自己粉饰成「我从未离婚」。

不对称在于**放下的重量与墓碑可见度**，而非「可变 vs 不可变」：

```text
Self-Report（你写的）   → 随时可 Retire，无需理由
Observation（世界写的） → 也可 Release，但更重、更慎重，墓碑更显眼持久
```

> **没有级联失效的 Release，是剧场，不是遗忘。** Release(seq) 必须找到所有 `cite(seq)` 的 Claim → 标记 stale → 强制重推导（evidence 中已无 seq）→ confidence 下降 / 论断推翻。否则你放下了事实，系统却仍「相信你是个失败者」。

---

## §6 — 共同署名（Co-authorship）

用户是自我模型的**共同作者**，不是被分析的对象。系统只能**提议**，由用户 Ratify / Reject / Revise / Release。

但共同署名**不等于用户独裁**（§1）：用户无权抹除事实与证据；系统有权持有诚实假设，但无权令其**定义你或驱动你**——除非经你署名。当用户的自陈与证据冲突，边界的职责是 **原样保全这道未和解的张力**，既不强加、也不谄媚。

> 系统越来越懂你，而你越来越不懂自己——这是推荐系统的病。Human Runtime 必须让用户**获得更多解释权**，而不是**被更多地解释**。

---

## §7 — 治理变更建议（底座聚焦阶段：建议性，非强制）

宪法的意义，是提醒未来那个想用「实现方便」挪动权力的人——但在 pre-PMF 单人阶段，不应让流程绑住迭代速度。

> **维护者 lint（建议）：** 这次改动是否改变了某条边界的 MUST、或 Authority Graph 中任何一方的否决权 / 行动权 / 否决权归属？
> - 否 → 是实现（§8），自由演化。
> - 是 → **建议**在 PR 中说明权力分配影响；待有真实用户与团队规模后再恢复强制修宪流程。

```text
绝不可因「实现方便」而被悄悄修改的，是「权力如何分配」，而非「代码如何组织」。
权力分配一旦为便利让步，数字自我就开始滑向数字人格管理器——
而这两者，只差几个字，却是两种哲学。
```

---

## §8 — 宪法之下（明确不在此冻结）

以下属于实现，可自由演化，**只要不违反 §1–§7 与序言**：

```text
Claim schema · Release lifecycle · Evidence graph · Confidence / decay model
Cross-model re-derivation · Connector 广度 · UI · Egress 具体策略 · 调度
Trajectory Registry · TrajectoryLinked · Identity Projection · verify_trajectory
```

认识论与轨迹理论 RFC（**v0.1 Experimental**，实现见 `backend/app/experimental/`）：

| 文档 | 内容 |
|------|------|
| [`rfc/MEANING_ONTOLOGY.md`](rfc/MEANING_ONTOLOGY.md) | Claim / Trajectory / Belief 三分与解释依赖 DAG |
| [`rfc/TRAJECTORY_RFC.md`](rfc/TRAJECTORY_RFC.md) | Trajectory 本体、Integrity、Registry 与物化 `trajectory_links` |
| [`rfc/IDENTITY_RFC.md`](rfc/IDENTITY_RFC.md) | Identity Projection、Narrative Honesty、`verify_identity` |
| [`rfc/IDENTITY_NARRATIVE_PROMPT.md`](rfc/IDENTITY_NARRATIVE_PROMPT.md) | LLM 叙事润色 prompt 与 `narrative_audit` 契约 |
| [`rfc/EPISTEMIC_CLOSURE_RFC.md`](rfc/EPISTEMIC_CLOSURE_RFC.md) | 解释闭环与 DAG / G5 / Egress 验收 |
| [`rfc/EGRESS_RFC.md`](rfc/EGRESS_RFC.md) | LLM 出站审计与 redact |
| [`rfc/CONNECTOR_RFC.md`](rfc/CONNECTOR_RFC.md) | 自我捕获连接器（calendar v0.1） |

> 路线先后：Egress + 连接器仍需早做——但其验收标准翻转：连接器不是「给 AI 工具」，而是「捕获自我的一个维度」；Egress 不是「防泄露的洁癖」，而是「我凭什么敢把『我是谁』喂给外部模型」的信任前提。

---

## §9 — 一句话总结

```text
Truth     禁止修改过去
Action    禁止越权行动
Data      禁止越权传播
Meaning   禁止垄断解释 + 必须支持在未解中行动

没有任何一方拥有全部权力。
保存的不是「你是谁」，而是「你如何持续成为你自己」。
```
