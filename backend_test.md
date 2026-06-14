# 后端 API 测试报告（第三轮）

**测试时间**: 2026-06-14 16:15 ~ 16:25  
**修复时间**: 2026-06-14 16:30 ~ 16:45  
**测试方式**: 通过 Python/curl 对运行在 `localhost:8000` 的后端服务进行全面的 HTTP API 黑盒测试  
**测试原则**: 只测不改（测试阶段）；后续已全部修复  
**本轮发现问题**: 8 个 — **已全部修复 ✅**

---

## 修复状态汇总

| 编号 | 问题 | 修复方式 | 状态 |
|------|------|----------|------|
| 1 | DELETE 任务未真正删除 | 新增 `TaskDeleted` 投影器，从 `tasks` 表删除记录 | ✅ |
| 2 | Goal 更新缺少 importance/urgency 校验 | 提取 `_validate_score_field`，PATCH/PUT 路径复用 | ✅ |
| 3 | Goal 更新缺少 status 枚举校验 | 新增 `VALID_GOAL_STATUSES` 白名单校验 | ✅ |
| 4 | Memory category 无枚举校验 | Pydantic `field_validator` 校验 7 种合法 category | ✅ |
| 5 | subtasks/tree 不存在返回空列表 | API 层增加父资源存在性检查，返回 404 | ✅ |
| 6 | stagnant/notifications 负数参数 | 添加 `Query(ge=1)` / `Query(ge=1, le=500)` 校验 | ✅ |
| 7 | 回顾触发器返回 Notification ID | trigger 函数始终返回 review record，notification 作为副作用 | ✅ |
| 8 | 回顾 AI 建议为占位文本 | LLM 生成建议；触发时自动刷新含占位符的旧回顾 | ✅ |

**回归测试**: 13/13 通过 ✅

---

## 一、严重问题（已修复）

### 1. DELETE 任务未真正删除，可重复删除

- **端点**: `DELETE /api/tasks/{task_id}`
- **修复**: `backend/app/core/runtime/kernel/projectors.py` 新增 `@projector("TaskDeleted")` 处理器
- **验证**: DELETE → GET 404 → 再次 DELETE 404 ✅

---

## 二、数据校验问题（已修复）

### 2. Goal 更新接口缺少 importance/urgency 边界校验

- **修复**: `backend/app/api/goals.py` 中 `_validate_goal_update_fields()` 在 PATCH/PUT 路径校验
- **验证**: `PATCH importance=2.0` → 400 ✅

### 3. Goal 更新接口缺少 status 枚举校验

- **修复**: 允许值 `active | completed | paused`
- **验证**: `PATCH status=totally_invalid` → 400 ✅

### 4. Memory 创建接口缺少 category 枚举校验

- **修复**: `backend/app/api/models.py` 中 `MEMORY_CATEGORIES` 枚举
- **合法值**: fact, preference, habit, belief, insight, work, personal
- **验证**: `POST category=invalid_cat` → 422 ✅

---

## 三、业务逻辑问题（已修复）

### 5. 回顾 AI 建议部分始终为占位符

- **修复**: `review_engine.py` 新增 `_generate_ai_suggestions_async()`；`_finalize_review_content()` 在润色后调用 LLM 生成建议
- **兼容**: `_ensure_ai_suggestions()` 在触发已有回顾时，检测占位符（含全角括号变体）并刷新
- **验证**: 触发 daily review 后 content 含真实 bullet 建议，无占位文本 ✅

### 6. 回顾触发器返回 Notification 对象而非 Review 对象

- **修复**: `daily_review.py` / `weekly_review.py` / `monthly_review.py` 始终返回 `review_engine.get_review()` 结果
- **验证**: trigger 返回 `type=daily` 的 review record，id 与 `GET /api/reviews/` 一致 ✅

---

## 四、一致性与幂等问题（已修复）

### 7. 不存在资源的查询返回空列表而非 404

- **修复**: `tasks.py` 中 `get_subtasks` / `get_task_tree` 增加存在性检查
- **验证**: 不存在 task/goal → 404 ✅

### 8. 部分 Query 参数缺少边界校验

- **修复**: `goals.stagnant` 添加 `Query(3, ge=1)`；`notifications.limit` 添加 `Query(50, ge=1, le=500)`
- **验证**: `days=-1` / `limit=-1` → 422 ✅

---

## 五、环境/配置观察（非代码 Bug）

| 观察项 | 详情 |
|--------|------|
| 健康状态 degraded | 6 个 MCP 服务器中 3 个缺少环境变量（brave/github/notion） |
| AUTH_TOKEN 未设置 | 无认证模式运行 |
| 邮箱未配置 | 测试邮箱连接返回「邮箱或密码未配置」 |
| LLM 连接正常 | deepseek-chat，latency ~1.5s |

---

## 六、全部端点测试覆盖汇总

| 类别 | 端点数 | 测试数 | 通过 |
|------|--------|--------|------|
| 根路径 | 1 | 1 | 1 |
| 系统/健康 | 11 | 18 | 18 |
| 对话/Chat | 8 | 18 | 18 |
| 目标/Goals | 10 | 24 | 24 |
| 任务/Tasks | 8 | 18 | 18 |
| 记忆/Memory | 8 | 14 | 14 |
| 通知/Notifications | 4 | 7 | 7 |
| 事件/Events | 1 | 7 | 7 |
| 知识库/Knowledge | 6 | 14 | 14 |
| 回顾/Reviews | 6 | 12 | 12 |
| 设置/Settings | 6 | 14 | 14 |
| 触发器/Triggers | 4 | 7 | 7 |
| 收件箱/Inbox | 5 | 9 | 9 |
| 遥测/Telemetry | 7 | 8 | 8 |
| 审批/Approvals | 4 | 6 | 6 |
| 后台任务 | 3 | 5 | 5 |
| WebSocket | 1 | 1 | 1 |
| 文档/OpenAPI | 3 | 3 | 3 |
| **总计** | **96** | **186** | **186** |

---

## 七、特殊场景测试

| 场景 | 结果 |
|------|------|
| SQL 注入 | ✅ 安全 |
| 超大请求体（10000 字符标题） | ✅ 正常 |
| 中文/Unicode/Emoji | ✅ 正常 |
| 空请求体/缺失必填字段 | ✅ 422/400 |
| 非法 JSON | ✅ 422 |
| 并发请求（5 并发创建 Goal） | ✅ 5/5 |
| 文件上传 / 空文件 | ✅ 200 / 400 |
| WebSocket ping/pong | ✅ pong |
| Chat SSE 流式对话 | ✅ 正常 |
| LLM 任务规划 | ✅ 正常 |
| 数据导出 | ✅ ~156KB 快照 |

---

## 八、修改文件清单

| 文件 | 变更 |
|------|------|
| `backend/app/core/runtime/kernel/projectors.py` | 新增 TaskDeleted 投影 |
| `backend/app/api/tasks.py` | subtasks/tree 404 检查 |
| `backend/app/api/goals.py` | 更新校验 + stagnant Query |
| `backend/app/api/models.py` | memory category 枚举 |
| `backend/app/api/notifications.py` | limit Query 边界 |
| `backend/app/core/review_engine.py` | AI 建议 LLM 生成 + 旧回顾刷新 |
| `backend/app/product/daily_review.py` | 返回 review record |
| `backend/app/product/weekly_review.py` | 返回 review record |
| `backend/app/product/monthly_review.py` | 返回 review record |
| `backend/tests/runtime/test_narrative_polish.py` | 更新异步测试 |
