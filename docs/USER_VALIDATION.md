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

## 已知问题（自用记录 · 2026-06-13）

### 1. `make dev` 启动时前端代理超时（ETIMEDOUT）

**现象：** `make dev` 后浏览器立刻打开，Vite 日志出现大量 `http proxy error: /api/... ETIMEDOUT`；过一会儿后端 MCP 日志才打完，刷新页面后恢复正常。

**原因：** 前后端并行启动。Vite ~1s 就绪并请求 `/api/*`，而后端仍在跑迁移 + 连接外部 MCP（Tavily、Context7 等），lifespan 完成前代理会超时。

**临时规避：**
```bash
# .env 中关闭外部 MCP，本地启动快很多
MCP_EXTERNAL_ENABLED=false
```
然后重启 `make dev`；或等终端出现 MCP `running on stdio` 后再刷新 http://localhost:5173。

**待修（可选）：** `make dev` 等 `/api/system/health` 就绪后再起前端。

### 2. 审批场景误显示「抱歉，未能生成回复」（已修 · 2026-06-13）

**现象：** 对话中触发需审批的工具（写文件、发邮件等）时，助手气泡先出现「抱歉，未能生成回复，请再试一次。」，审批弹窗正常弹出；批准后才显示真实结果。

**原因：** 后端在 `confirmation_required` 后以空文本发送 `done`；前端 `useChatMessages.ts` 在 `done` 时若 `tempContent` 为空就填入兜底错误文案，未区分「等待审批」与「真正失败」。

**修复：** `confirmation_required` 后 `done` 不再填兜底文案；仅无审批且无文本时才显示错误提示。

**验证：** `frontend/src/components/chat/ChatView.test.tsx` — 审批流不应出现「未能生成回复」。

### 3. 工具调用 DSML 标记泄露到对话气泡（已修 · 2026-06-13）

**现象：** 助手回复里直接显示 `<｜｜DSML｜｜tool_calls>…invoke name="read_file"…` 等原始标记，工具可能未真正执行。

**原因：** 部分 LLM（如 DeepSeek）偶发把工具调用写进 `delta.content` 文本流，而非结构化 `delta.tool_calls`；前端原样渲染。

**修复：** 后端 `tool_markup.py` 过滤流式 DSML 并解析为 `tool_calls`；前端/读库/存库三层剥离；**需重启 `make dev`** 后生效，旧对话刷新后也会清理历史气泡。

**验证：** `backend/tests/runtime/test_tool_markup.py`、`frontend/src/utils/stripToolMarkup.test.ts`

### 4. 审批后 LLM 不继续完成任务（已修 · 2026-06-14）

**现象：** 用户审批通过工具操作后，助手气泡显示"任务完成"但没有后续文本回复，对话就此停止。

**排错过程（含失误记录）：**

本轮 bug 修复经历了 3 次迭代才找到根因：

1. **第一轮（只改前端，无效）：** 看到聊天界面有 `<｜tool_calls>` 标记泄露 → 推测前端 `stripToolMarkup` 的 `invoke()` 正则定义了但未调用 → 增加调用和扩展 `tail()` 正则。用户反馈"没有解决"。

2. **第二轮（只改前端，治标不治本）：** 重写前端剥离为 5 层级联防御，在 MessageItem 和审批流中都加防御 → 标记消失了，但 LLM 仍然没有继续执行任务。

3. **第三轮（查数据库，找到根因）：** 通过 `sqlite3` 直接查询 `messages` 表，发现了真正的因果链：

```sql
-- Message 9 的内容（已保存到数据库）
SELECT id, role, content FROM messages WHERE conversation_id = ? ORDER BY created_at;
```

| 序号 | role | 内容 |
|------|------|------|
| 8 | tool | `{"error": "Shell metacharacters ... not allowed"}` |
| **9** | **assistant** | **`<｜tool_calls>…<｜invoke>…pwd…</｜invoke>…</｜tool_calls>`** |

- Message 9 保存的是**纯工具标记文本**（不含正常的自然语言），经 `strip_tool_markup` 剥离后变为 **空字符串**。
- 这条空消息由 `continue_after_tool_result` 产出：LLM 在被请求做**纯文本**回复时，仍然用结构化工具调用语法输出，导致剥离后为空。

**根因：** `continue_after_tool_result` 使用非流式、不传 `tools` 的方式调用 DeepSeek，但 DeepSeek 仍以文本形式输出工具标记 → `strip_tool_markup` 剥离后为空 → 没有内容被保存/展示。

**修复：**
1. `brain.py` 的 `continue_after_tool_result` 增加空响应检测 + 重试：空内容时自动追加"禁止工具调用"的中文提示再请求一次。
2. `tool_markup.py` 的 `strip_tool_markup` 防御层从 3 层增到 4 层（完整块 → 独立 invoke → 残余标签 → `<｜` 终极截断）。
3. `stripToolMarkup.ts` 前端同步升级到 5 层防御。

**教训（为什么改了多次才改对）：**

| 失误 | 后果 | 正确做法 |
|------|------|----------|
| 没查数据库就改代码 | 前两轮都在修"显示"问题，漏了真正的"行为"问题 | **先读数据，再动手**：`sqlite3` 查 `messages` 表能 30 秒定位根因 |
| 只改了前端 | 标记被隐藏，但 LLM 空响应没解决 | 按**端到端数据流**走查：LLM → 后端 → DB → 前端 |
| 没区分"症状"与"根因" | 把标记泄露当根因修了两轮 | 问自己："如果标记被剥离了，任务能继续吗？"——不能，因为剥离后内容是空的 |

**验证：**
- 后端：`backend/app/core/agents/brain.py` → `continue_after_tool_result` 的 retry 分支有测试覆盖
- 前端：`frontend/src/utils/stripToolMarkup.test.ts`
