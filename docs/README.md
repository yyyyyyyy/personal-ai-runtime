# 文档索引

本仓库文档集中在 `docs/`。根目录仅保留 [README](../README.md)。

## 架构与治理

| 文档 | 说明 |
|------|------|
| [RUNTIME_SPEC.md](RUNTIME_SPEC.md) | Personal AI Runtime 架构规格（7 Primitive 冻结） |
| [HUMAN_RUNTIME_CONSTITUTION.md](HUMAN_RUNTIME_CONSTITUTION.md) | 认识论宪法、Meaning Boundary 与权力结构 |

阅读顺序建议：**RUNTIME_SPEC**（系统怎么工作）→ **宪法**（系统为谁、不能做什么）→ **RFC**（Meaning / Trajectory / Identity 理论展开）。

## RFC（v0.1 Ratified）

| 文档 | 说明 |
|------|------|
| [rfc/MEANING_ONTOLOGY.md](rfc/MEANING_ONTOLOGY.md) | Claim / Trajectory / Belief 三分与解释依赖 DAG |
| [rfc/TRAJECTORY_RFC.md](rfc/TRAJECTORY_RFC.md) | Trajectory 本体、Registry、物化 `trajectory_links` |
| [rfc/IDENTITY_RFC.md](rfc/IDENTITY_RFC.md) | Identity Projection、Narrative Honesty |
| [rfc/IDENTITY_NARRATIVE_PROMPT.md](rfc/IDENTITY_NARRATIVE_PROMPT.md) | LLM 叙事润色 prompt 与 `narrative_audit` 契约 |
| [rfc/EPISTEMIC_CLOSURE_RFC.md](rfc/EPISTEMIC_CLOSURE_RFC.md) | 解释闭环、DAG / G5 / Egress 验收 |
| [rfc/EGRESS_RFC.md](rfc/EGRESS_RFC.md) | LLM 出站审计与 redact |
| [rfc/CONNECTOR_RFC.md](rfc/CONNECTOR_RFC.md) | 日历只读连接器（Experience 捕获） |

宪法 §8 与 RFC 序言互为入口；细节以各 RFC 正文为准。
