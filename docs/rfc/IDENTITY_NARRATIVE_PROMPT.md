# Identity Narrative Prompt · RFC Appendix

> LLM 润色 Identity Projection 文稿时的 **MUST** 约束与 `narrative_audit` 回填规范。  
> 依赖：`IDENTITY_RFC.md` N1–N5、`MEANING_ONTOLOGY.md`  
> 状态：**v0.1 — Experimental**（与 backend experimental narrative_audit 实现对齐）

---

## §1 — Role

模型在此阶段是 **Projection Weaver**，不是 Identity Oracle：

- 输出 MUST 标注为系统投影草稿
- MUST NOT 输出「你就是…」「你一直是…」式人格定论（除非用户已 ratify 的 self-report 原文引用）
- MUST 并列呈现竞争轨迹（N4）
- MUST NOT 用后期 Outcome 证明前期选择（N3）

---

## §2 — System Prompt Block（复盘 / 叙事润色）

```text
你正在生成 Identity Projection 草稿（非身份认定）。

规则：
1. 开篇保留「系统投影草稿」免责声明。
2. 轨迹：列举所有 active 竞争对；标注 identity_narrative_opt_in 状态；禁止只写一条线。
3. Claim/Belief：仅用「系统推测」「可能」「模式假设」；proposed 不得写作定论。
4. 禁止 Outcome Backfill：不得写「事实证明你当年是对的」。
5. 结尾：提醒用户可在「记忆」「轨迹」页署名或争议。

输出后须可被 narrative_audit 解析（见 §3）。
```

---

## §3 — `narrative_audit` 回填（实现契约）

润色完成后，Runtime MUST 合并或校验以下字段（`build_narrative_audit` 已覆盖模板路径；LLM 路径 MUST 不削弱）：

| 字段 | 必填 | 说明 |
|------|------|------|
| `cited_trajectory_ids` | ✅ | 正文引用的轨迹 id |
| `cited_beliefs` | 若有 | `{memory_id, claim_status, excerpt}` |
| `identity_claims` | 若有 | `{text, evidence_event_seqs[], evidence_types[]}` |
| `outcome_event_seqs` | 若有 | 引用的 Outcome 事件 seq |

**硬失败（I-F*）** 由 `identity_lint.py` 在落库前执行；WARN（I-W*）写入 CI 日志。

---

## §4 — 与 Agency 防火墙

叙事润色 MUST NOT：

- 修改 Goal 排序、Brief、Today 排名
- 自动 `ratify` Trajectory 边或 Belief
- 将 proposed Trajectory 写成已授权身份叙事（须 `TrajectoryIdentityOptIn`）

---

*See also: `IDENTITY_RFC.md`, `backend/app/core/runtime/projection/narrative_audit.py`*
