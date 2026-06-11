# 用户验证计划（阶段 4）

> 目标：用 5–20 个真实用户验证留存，再决定 Meaning 实验层去留。

## 提供的能力（聚焦底座）

- 对话 + 23 个 MCP 工具（含审批）
- 目标 / 记忆 / 收件箱
- **一键无损导出**（`POST /api/system/export`）— 完整 `event_log` + 对话

## 不提供（默认关闭）

- Meaning Gate 叙事过滤（`MEANING_GATE_ENABLED=false`）
- Trajectory 自动链接（`EXPERIMENTAL_TRAJECTORY_ENABLED=false`）

## 招募

1. 知识工作者 / 独立开发者，已有「第二大脑」需求
2. 愿意本地运行（Docker 或 `make dev`）
3. 连续使用 2 周

## 核心指标

| 指标 | 目标 |
|------|------|
| D7 留存 | ≥ 40% |
| 导出使用率 | ≥ 1 次/用户 |
| 主动对话天数 | ≥ 3 天/周 |

## 决策规则

- **D7 < 20%：** 封存 Meaning 层，只做底座 + 助手
- **D7 ≥ 40% 且用户索要「自我叙事」：** 重新启用 `experimental/` 并做小范围 A/B
