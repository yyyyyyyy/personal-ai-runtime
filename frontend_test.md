# 前端测试报告

**测试时间**: 2026-06-14 16:55 ~ 17:10  
**测试方式**: Vitest 单元测试、TypeScript 编译、生产构建、Playwright E2E、对运行在 `localhost:5173`（前端）+ `localhost:8000`（后端）的 Live 集成测试  
**测试原则**: 只测不改  
**本轮发现问题**: 7 个（含 1 个严重、3 个中等、3 个轻微/体验）

---

## 测试汇总

| 类别 | 结果 | 说明 |
|------|------|------|
| Vitest 单元测试 | ✅ 72/72 通过 | 18 个测试文件 |
| TypeScript (`tsc --noEmit`) | ✅ 通过 | 无类型错误 |
| 生产构建 (`npm run build`) | ✅ 通过 | 有 chunk 体积警告 |
| Playwright E2E | ❌ 0/6 通过 | mock 路由 glob 过宽导致白屏 |
| Live 页面路由（8 页） | ✅ 8/8 通过 | 真实后端联调 |
| Live 交互场景 | ✅ 18/21 通过 | 见下文详细场景 |
| API 代理连通性 | ✅ 核心端点正常 | 见附录 |

---

## 一、严重问题

### 1. Playwright E2E 测试全部失败 — mock 路由拦截 Vite 源码模块

- **文件**: `frontend/e2e/chat-approval.spec.ts`
- **现象**: 6 个 E2E 测试全部失败；首页 `#root` 为空，找不到「欢迎回来」、侧边栏链接、聊天输入框等任何 UI
- **根因**: `page.route()` 使用的 glob 模式过宽，例如：
  - `**/api/notifications**` 会匹配 `http://localhost:5173/src/api/notifications.ts`
  - `**/api/goals**` 会匹配 `http://localhost:5173/src/api/goals.ts`
  - 同理影响 `reviews.ts`、`inbox.ts`、`approvals.ts` 等源码模块
- **浏览器控制台错误**:
  ```
  Failed to load module script: Expected a JavaScript-or-Wasm module script
  but the server responded with a MIME type of "application/json"
  ```
- **对比**: 不使用 mock、直连真实后端的 Live Playwright 测试可正常渲染全部页面
- **建议修复**: mock 模式改为精确 API 路径，例如 `**/api/notifications*`（仅匹配 `/api/notifications` 开头的请求），或使用 `route.request().url().includes('/api/')` 过滤

---

## 二、中等问题

### 2. 设置页未展示后端 `degraded` 健康状态

- **页面**: `/settings`
- **现象**: 后端 `GET /api/system/health` 返回 `status: "degraded"`，`startup.warning_count: 1`（MCP 6 个服务器中 3 个连接失败）
- **前端表现**: 设置页「系统状态」卡片仅显示版本号、认证状态、对话/目标/记忆计数，**不显示**整体健康状态或 MCP 告警
- **影响**: 用户无法从 UI 感知系统降级，可能误以为一切正常
- **建议**: 在设置页或仪表盘增加 `health.status` / `startup.checks.mcp` 的可视化告警

### 3. 仪表盘「主动建议 & 通知」在全部已读时为空

- **页面**: `/dashboard`
- **现象**: 当前环境 4 条通知（含 3 条复盘）均已标记 `read: 1`；仪表盘仅拉取 `listNotifications(10, unread_only=true)`，导致该区域显示「暂无主动建议」
- **对比**: 侧边栏通知铃铛可正常列出全部 4 条历史通知
- **影响**: 用户回到仪表盘无法快速回顾已读复盘/简报，需去时间线或通知铃铛
- **建议**: 仪表盘同时展示最近 N 条通知（含已读），或提供「查看全部」入口

### 4. 历史复盘通知内容缺少 `@related:` 前缀且为快照

- **数据**: 现有 3 条 `type=review` 通知的 `content` 均不含 `@related:{review_id}` 前缀
- **现象**:
  - 通知 `content` 仍含占位文本「（将由 LLM 根据以上数据生成个性化建议）」
  - 对应 review 记录经 API 拉取后多数已更新（无占位符）
- **前端缓解**: `NotificationDetailModal` 对 review 类型会调用 `getReview()` 拉取最新内容；标题匹配 fallback（`findReviewForNotification`）在当前数据下可正确关联
- **Live 验证**: 通知铃铛点击复盘 → 弹窗显示完整最新内容 ✅
- **残留风险**: 若标题格式变化或存在同周期多条 review，fallback 可能匹配失败；新通知应写入 `@related:` 前缀（后端已支持，旧数据未回填）

---

## 三、轻微问题 / 体验改进

### 5. 无效目标 URL 错误提示过于简略

- **场景**: 访问 `/goals/00000000-0000-0000-0000-000000000000`
- **API**: `GET /api/goals/{id}` → 404，`detail: "Goal not found"`
- **前端**: 右上角 toast 仅显示 `[目标] 错误`，未展示具体原因；详情面板保持空白
- **建议**: toast 显示 API 返回的 `detail`；详情区展示「目标不存在」空状态

### 6. WebSocket 直连后端端口，不经 Vite 代理

- **文件**: `frontend/src/hooks/useNotifications.ts`
- **行为**: WS 连接 `ws://localhost:8000/ws`（通过 `__API_PORT__` 编译常量）
- **开发环境**: 当前可正常工作（无控制台 WS 错误）
- **部署风险**: 若生产环境仅暴露 5173/443 单端口、8000 不对外，实时通知推送将失效
- **建议**: 生产构建通过同源 `/ws` 代理，或配置化 WS URL

### 7. 生产构建 JS chunk 超过 500KB

- **构建输出**:
  ```
  dist/assets/index-D5bLtkd4.js   1,196.59 kB │ gzip: 397.01 kB
  (!) Some chunks are larger than 500 kB after minification.
  ```
- **影响**: 首屏加载偏慢，无功能错误
- **建议**: 路由级 code-splitting（`React.lazy`）或手动 chunks

---

## 四、已通过项（Live 联调）

### 4.1 页面路由与导航

| 路由 | 结果 | 关键元素 |
|------|------|----------|
| `/` | ✅ | 「下午好，欢迎回来」、快捷入口、开始新对话 |
| `/goals` | ✅ | 目标列表（13 条）、新建按钮 |
| `/goals/:id` | ✅ | 详情、删除按钮、行动步骤 |
| `/inbox` | ✅ | 收件箱看板加载正常 |
| `/memories` | ✅ | 分组记忆列表 |
| `/knowledge` | ✅ | 文档列表（1 篇） |
| `/dashboard` | ✅ | 系统运行概览、Token/成本/工具/记忆统计 |
| `/timeline` | ✅ | 事件时间线 + 复盘卡片 |
| `/settings` | ✅ | 数据主权、导出按钮、LLM/邮箱配置 |
| 侧边栏导航 | ✅ | 对话→目标→时间线 跳转正常 |

### 4.2 交互场景

| 场景 | 结果 | 备注 |
|------|------|------|
| 目标列表加载 | ✅ | 无「加载目标失败」toast |
| 目标详情 + 删除按钮 | ✅ | 选中目标后「删除」按钮可见 |
| 时间线复盘卡片 → 详情弹窗 | ✅ | 可打开，含完整复盘正文 |
| 通知铃铛 → 复盘详情 | ✅ | 拉取最新 review 内容，无占位符 |
| 聊天页输入框 + 发送 | ✅ | 已有对话可正常进入 |
| 上下文面板 → 待审批 | ✅ | 展开后显示 4 条 pending approval |
| 首页本周回顾卡片 | ✅ | 有 weekly review 时展示 |
| 记忆/知识库加载 | ✅ | 无加载失败 toast |
| 无效 goalId 不崩溃 | ✅ | 应用保持稳定 |

### 4.3 API 代理（经 `localhost:5173/api`）

| 端点 | HTTP | 说明 |
|------|------|------|
| `/api/system/health` | 200 | status=degraded |
| `/api/system/info` | 200 | |
| `/api/goals/` | 200 | 13 条 |
| `/api/chat/conversations` | 200 | |
| `/api/notifications/?limit=15` | 200 | 4 条 |
| `/api/reviews/?limit=5` | 200 | 5 条 |
| `/api/events/?limit=50` | 200 | |
| `/api/memory/memories/grouped` | 200 | |
| `/api/knowledge/documents` | 200 | |
| `/api/telemetry/*` | 200 | cost/tool/memory/health |
| `/api/settings/llm` | 200 | |
| `/api/approvals/?pending_only=true` | 200 | 4 条 pending |

---

## 五、历史/环境观察（非代码缺陷）

### Vite 代理瞬时错误

- **终端日志**（`frontend` dev server）在 backend 重启期间出现：
  ```
  [vite] http proxy error: /api/goals/
  Error: read ECONNRESET / ECONNREFUSED / ETIMEDOUT
  ```
- **复测**: 当前前后端均稳定时，上述 API 全部 200
- **结论**: 后端不可用时的预期表现；前端 `errorStore.backendUnavailable` 会显示顶部红条

### 后端健康降级

- MCP: 6 个 server，3 connected / 3 failed
- 不影响前端页面渲染，但可能影响依赖 MCP 工具的功能

---

## 六、测试覆盖缺口

| 缺口 | 说明 |
|------|------|
| E2E 审批流 | 因 mock 问题未验证确认/取消对话框 |
| 目标删除端到端 | 未执行实际 DELETE（避免污染数据） |
| 记忆/知识库 CRUD | 未执行写操作 |
| 邮件轮询 / 简报刷新 | 未触发 |
| 生产 `preview` 模式 | 未测 |
| 前端 ESLint | `package.json` 无 lint 脚本 |

---

## 七、问题优先级建议

| 优先级 | 编号 | 问题 | 建议 |
|--------|------|------|------|
| P0 | 1 | E2E mock 拦截源码 | 收窄 glob，修复后 E2E 可纳入 CI |
| P1 | 2 | 设置页不显示 degraded | 增加健康/MCP 状态展示 |
| P1 | 3 | 仪表盘已读通知不可见 | 展示最近通知或链接到铃铛 |
| P2 | 4 | 旧通知无 @related: | 后端回填或前端仅依赖 API 拉取 |
| P2 | 5 | 无效 goal 错误文案 | 展示 API detail + 空状态 |
| P3 | 6 | WS 直连 8000 | 部署方案需同源代理 |
| P3 | 7 | JS bundle 过大 | 按需拆分 |

---

## 八、结论

前端在 **真实后端联调** 下整体可用：8 个主要页面均可加载，目标/复盘/通知/聊天/上下文面板等核心交互经验证正常。单元测试与构建均通过。

主要风险集中在 **E2E 测试基础设施**（mock 路由导致白屏，CI 中 `npm run test:e2e` 当前不可用）以及 **系统健康/通知的可发现性**（degraded 状态与已读通知在 UI 中不够明显）。建议优先修复 E2E mock 模式，再补充健康状态与通知列表的体验优化。
