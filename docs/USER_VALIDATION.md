# 自用验证计划（Dogfood）

> 目标：在没有外部用户时，用**自己连续真实使用 2 周**验证产品是否值得继续投入。
> 你自己就是最合格的 N=1 用户——用真实邮件、真实目标、真实对话，每个不爽的瞬间都值得记录。

## 怎么用

1. **每天真实使用** — 对话、查收件箱、管目标，不要「演示式」点几下就关。
2. **不爽就记一条** — 摩擦点进 `event_log`，可导出、可统计：
   ```bash
   # 命令行（后端运行时或独立脚本均可）
   cd backend && python3 scripts/friction.py "这里让我卡住了：……"
   cd backend && python3 scripts/friction.py "审批文案看不懂" --area tools --severity high
   cd backend && python3 scripts/friction.py --list --status open
   ```
   或通过 API：
   ```bash
   curl -X POST http://localhost:8000/api/system/friction \
     -H "Content-Type: application/json" \
     -d '{"note":"收件箱摘要太长","area":"inbox","severity":"medium"}'
   ```
3. **每周看一眼指标**：
   ```bash
   curl http://localhost:8000/api/system/validation-metrics
   ```
4. **至少导出一次** — 验证数据主权链路你真的信得过：
   ```bash
   curl -X POST http://localhost:8000/api/system/export \
     -H "Content-Type: application/json" \
     -d '{"confirm":"EXPORT_ALL_DATA"}' -o backup.json
   ```

## 核心指标（单人版）

| 指标 | 目标 | 说明 |
|------|------|------|
| 主动对话天数 | ≥ 3 天/周 | `active_chat_days_7d` |
| 导出至少 1 次 | ✅ | `export_count ≥ 1` |
| 摩擦点有记录 | 用着不爽就记 | `friction.logged_7d`；开放项 `friction.open_total` |

`/api/system/validation-metrics` 返回 `mode: "dogfood"` 及上述字段。

## 决策规则（2 周后）

- **几乎不用（活跃 < 1 天/周）：** 先砍门槛（上手成本、mock demo），别加功能。
- **经常用但摩擦点多：** 按 `friction.by_area_7d` 排序，优先修最高频区域。
- **经常用且摩擦少：** 考虑重新尝试小范围招募，或深化尖刀场景（如收件箱体验闭环）。

## 可选：未来外部验证

若之后能招募到 5–20 人，可恢复队列留存指标（D7 ≥ 40% 等）。在此之前，**单人 dogfood 数据比零用户更有决策价值**。

## 提供的能力（聚焦底座）

- 对话 + 24 个 MCP 工具（含审批）
- 目标 / 记忆 / 收件箱
- **一键无损导出**（`POST /api/system/export`）— 完整 `event_log` + 对话
