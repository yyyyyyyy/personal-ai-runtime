# 文档索引

本仓库文档集中在 `docs/`。根目录仅保留 [README](../README.md)。

## 当前阶段：底座聚焦（2026-06）

v1.0 冻结 / 修宪流程**已暂停**。优先补齐：

- 无损 Event Log 导出/导入（数据主权护城河）
- 对话纳入 Event Log（`MessageAppended` 投影）
- 投影快照（增量 rebuild）
- 安全威胁模型（Prompt Injection / Egress 审计）

Meaning / Trajectory / Identity 层为**实验性**设计，代码在 `backend/app/experimental/`。

## 架构与治理

| 文档 | 说明 |
|------|------|
| [RUNTIME_SPEC.md](RUNTIME_SPEC.md) | Personal AI Runtime 架构规格（7 Primitive，Draft） |
| [HUMAN_RUNTIME_CONSTITUTION.md](HUMAN_RUNTIME_CONSTITUTION.md) | 认识论治理参考（Draft，非强制） |
| [THREAT_MODEL.md](THREAT_MODEL.md) | 信任边界与 Prompt Injection 威胁模型 |

阅读顺序建议：**RUNTIME_SPEC**（系统怎么工作）→ **THREAT_MODEL**（安全边界）→ 宪法/RFC（实验性理论展开）。

## RFC（v0.1 Experimental）

| 文档 | 说明 |
|------|------|
| [rfc/MEANING_ONTOLOGY.md](rfc/MEANING_ONTOLOGY.md) | Claim / Trajectory / Belief 三分与解释依赖 DAG |
| [rfc/TRAJECTORY_RFC.md](rfc/TRAJECTORY_RFC.md) | Trajectory 本体、Registry、物化 `trajectory_links` |
| [rfc/IDENTITY_RFC.md](rfc/IDENTITY_RFC.md) | Identity Projection、Narrative Honesty |
| [rfc/IDENTITY_NARRATIVE_PROMPT.md](rfc/IDENTITY_NARRATIVE_PROMPT.md) | LLM 叙事润色 prompt 与 `narrative_audit` 契约 |
| [rfc/EPISTEMIC_CLOSURE_RFC.md](rfc/EPISTEMIC_CLOSURE_RFC.md) | 解释闭环、DAG / G5 / Egress 验收 |
| [rfc/EGRESS_RFC.md](rfc/EGRESS_RFC.md) | LLM 出站审计（非脱敏边界） |
| [rfc/CONNECTOR_RFC.md](rfc/CONNECTOR_RFC.md) | 日历只读连接器（Experience 捕获） |

宪法 §8 与 RFC 序言互为入口；细节以各 RFC 正文为准。
