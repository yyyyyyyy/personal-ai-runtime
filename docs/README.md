# 文档索引

本仓库文档集中在 `docs/`。根目录仅保留 [README](../README.md)。

## 当前阶段：底座聚焦 + 用户验证

优先事项：

- 无损 Event Log 导出/导入（数据主权护城河）
- 对话纳入 Event Log（`MessageAppended` 投影）
- 投影快照（增量 rebuild）
- 安全威胁模型（Prompt Injection / Egress 审计）
- 招募真实用户验证留存（见 `USER_VALIDATION.md`）

## 文档

| 文档 | 说明 |
|------|------|
| [ONBOARDING.md](ONBOARDING.md) | 5 分钟上手：配置 → 启动 → 验证 → 导出数据 |
| [RUNTIME_SPEC.md](RUNTIME_SPEC.md) | 架构规格：Runtime Primitive、Kernel Boundary、Read Surface |
| [THREAT_MODEL.md](THREAT_MODEL.md) | 信任边界与 Prompt Injection 威胁模型 |
| [USER_VALIDATION.md](USER_VALIDATION.md) | 用户验证计划与留存指标 |

阅读顺序：**ONBOARDING**（跑起来）→ **RUNTIME_SPEC**（怎么工作）→ **THREAT_MODEL**（安全边界）。
