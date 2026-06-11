# Epistemic Closure · RFC v0.1

> 定义 Meaning 层「解释闭环」的闭合条件，与向上生成禁止、G5、Egress 信任链的关系。  
> 状态：**v0.1 — Experimental** ｜ 适配基线：backend v0.9.0  
> 依赖：[`MEANING_ONTOLOGY.md`](MEANING_ONTOLOGY.md) §3、`verify_meaning_dag.py`

---

## §1 — 问题

**解释闭环（Epistemic Closure）** 指：高层 Meaning 对象在缺乏低层证据的情况下，自行生成或改写低层对象，从而形成系统垄断叙述路径。

例：用 Belief 聚合直接 emit `TrajectoryLinked`；用 Trajectory 直接 emit `BeliefFormed` 而无 Pattern/证据链。

## §2 — 闭合条件（MUST）

1. **向上生成禁止** — 见 Ontology §3.2；由 `verify_meaning_dag.py` 验收  
2. **向下引用显式** — `evidence_chain` / `event_seq` / `cited_*` 字段不得省略  
3. **Agency 防火墙** — G5：`agency_gate.py` 阻止 unratified Meaning 影响排序  
4. **出站信任** — LLM Egress 对 identity/memory 上下文分类与 redact（`EGRESS_RFC.md`）

## §3 — 与宪法的关系

| 宪法边界 | Closure 角色 |
|----------|----------------|
| Meaning §4 | 保全张力；Closure 防垄断路径 |
| Data Egress | 外部模型不可获得未裁决的 identity 真值 |
| Truth | Event 不可篡改；Closure 不替代 Event Sourcing |

## §4 — 验收

- `verify_meaning_dag.py` — FAIL on §3.2 violations  
- `verify_agency_surfaces.py` — G5 runtime  
- `verify_egress.py` — LLM outbound audit  
- `verify_epistemic_closure.py` — 占位；v0.2 聚合上述脚本

---

*See also: [`HUMAN_RUNTIME_CONSTITUTION.md`](../HUMAN_RUNTIME_CONSTITUTION.md), [`EGRESS_RFC.md`](EGRESS_RFC.md).*
