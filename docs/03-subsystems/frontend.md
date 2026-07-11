# 前端子系统

本文档描述 React SPA（`frontend/`）。技术栈：React 19 + Vite 6 + TanStack Query 5 + Zustand 5 + Tailwind v4 + react-router-dom 7。

## 启动

[`frontend/src/main.tsx`](../../frontend/src/main.tsx)：

- 挂载 `<RouterProvider router={router} />` 包在 `QueryClientProvider` 内。
- `QueryClient` 默认：`staleTime 30s`、`refetchOnWindowFocus: false`、`retry: 1`。
- `import "./auth"` 在模块加载时跑 `initAuth()`。
- 生产模式注册 Service Worker `/sw.js`。

## 路由

[`frontend/src/router.tsx`](../../frontend/src/router.tsx) 用 `createBrowserRouter`，**所有页面组件懒加载**，嵌套在单个 `Layout` 下：

| Route | 页面文件 | 用途 |
|---|---|---|
| `/`（index） | `pages/ChatPage.tsx` | 聊天首页（无会话）→ `ChatHome` |
| `/chat/:conversationId` | `pages/ChatPage.tsx` | 活跃会话 → `ChatView` |
| `/goals` | `pages/Goals.tsx` | 目标列表 + 详情 |
| `/goals/:goalId` | `pages/Goals.tsx` | 目标详情 |
| `/inbox` | `pages/Inbox.tsx` | 邮件分拣 |
| `/memories` | `pages/Memories.tsx` | 记忆列表 + 图谱 |
| `/portrait` | `pages/Portrait.tsx` | AI 用户画像 |
| `/trust` | `pages/TrustReport.tsx` | 信任报告 / 数据主权 |
| `/demo` | `pages/ModelSwitchDemo.tsx` | 跨模型记忆连续性演示 |
| `/dashboard` | `pages/Dashboard.tsx` | 总览仪表盘 |
| `/settings` | `pages/Settings.tsx` | LLM/邮件/MCP/数据设置 |
| `/approvals` | `pages/Approvals.tsx` | 审批队列 |
| `/timeline` | `pages/Timeline.tsx` | 人生事件时间线 |
| `/knowledge` | `pages/Knowledge.tsx` | RAG 文档上传与搜索 |

## 认证

[`frontend/src/auth.ts`](../../frontend/src/auth.ts)：

**Token 解析顺序**：`import.meta.env.VITE_AUTH_TOKEN`（构建/env）→ `localStorage["auth_token"]` → 无。选中 token 在 React 挂载前经 `setAuthToken()` 推入 API client。`initAuth()` 在模块 import 时调用。

## API Client 分层

[`frontend/src/api/`](../../frontend/src/api/) 是分层结构：

```
core.ts        ← fetch 包装 + auth header + ApiError
   ↑
chat.ts, system.ts, goals.ts, memory.ts, inbox.ts,
settings.ts, telemetry.ts, approvals.ts,
notifications.ts, portrait.ts, trustReport.ts
   ↑
client.ts      ← barrel 再导出（向后兼容）
types.ts       ← 共享 TS 接口
```

### core.ts

[`frontend/src/api/core.ts`](../../frontend/src/api/core.ts)：

- `API_BASE = "/api"` — **始终相对**。开发经 Vite proxy；生产同源部署。
- Auth header：`Authorization: Bearer <token>`（仅当 token 设置）。
- 401 → 抛 `ApiError`（中文消息「认证失败，请检查 AUTH_TOKEN 与 VITE_AUTH_TOKEN 是否一致」）。
- `ApiError` 带 `.status` 字段。

### 前端如何到达后端

**开发模式** — Vite proxy（[`frontend/vite.config.ts:11-28`](../../frontend/vite.config.ts)）：

```
"/api" → http://${API_HOST}:${API_PORT}   (changeOrigin: true)
"/ws"  → http://${API_HOST}:${API_PORT}   (ws: true, changeOrigin: true)
```

`API_HOST`/`API_PORT` 来自 `process.env.VITE_API_HOST`/`VITE_API_PORT`（默认 `localhost`/`8000`）。配置从**仓库根** `.env`（`envDir: rootDir`）读取——与后端 `AUTH_TOKEN` 同一个文件。

**生产模式** — `API_BASE = "/api"` 相对，要求同源部署同时服务静态前端与 API。

### SSE 聊天流

[`frontend/src/api/chat.ts:30-114`](../../frontend/src/api/chat.ts) 的 `sendMessage()` 开流式 POST，手动解析 SSE：

- 读 `data: ` 行，解码 JSON `StreamEvent`。
- 事件类型：`text_delta`、`tool_call_start`、`tool_result`、`confirmation_required`、`sources`、`done`、`error`、`ping`（跳过）。
- 30s 空闲超时中止 reader。
- Auth header 直接附加（不走 `request()`）。

## 状态管理

### Zustand stores（[`frontend/src/stores/`](../../frontend/src/stores/)）

- **`chatStore.ts`** — 全局聊天 UI 状态：`conversations`、`activeConversationId`、`pendingPrompt`（被 `useQuickChat` 用于播种新聊天）。
- **`errorStore.ts`** — 全局错误/toast 队列：`errors`（上限 5）、`backendUnavailable` 标志（`Layout` 初始健康检查失败时翻转）、`addError`/`dismissError`/`setBackendUnavailable`/`clearErrors`。

### TanStack React Query

主要用于 server cache：

- `useDashboard`（[`hooks/useDashboard.ts:30-139`](../../frontend/src/hooks/useDashboard.ts)）— 7 个并行查询（`costSummary`/`costByModel`/`toolSummary`/`memoryStats`/`health`/`notifications`/`dashboard`），全部 `refetchInterval: 60_000`、`staleTime: 30_000`、`retry: 1`。
- `useMemoriesGroupedQuery`（[`hooks/useMemoriesQuery.ts:19-35`](../../frontend/src/hooks/useMemoriesQuery.ts)）— query key `["memories","grouped"]`、`staleTime: 10s`。
- 共享 query key 集中在 [`hooks/useWsInvalidationBridge.ts:13-19`](../../frontend/src/hooks/useWsInvalidationBridge.ts)：`memories`、`memoriesGrouped`、`goals`、`inbox`、`dashboard`。

### WebSocket 失效桥

[`hooks/useWsInvalidationBridge.ts`](../../frontend/src/hooks/useWsInvalidationBridge.ts)：轻量 pub/sub。`useNotifications`（持有 WS）对每个合法 payload 调 `dispatchWsEvent(raw)`，桥订阅并失效 React Query cache：

- `memory_changed` → 失效 `memories` + `dashboard`
- `notification` → 失效 `dashboard`
- 其他类型忽略（显式 opt-in）

`Layout` 根挂载一次。

## 自定义 Hooks

| Hook | 文件 | 职责 |
|---|---|---|
| `useChatMessages` | [`useChatMessages.ts:139-334`](../../frontend/src/hooks/useChatMessages.ts) | 加载消息、管理流式状态、解析 tool calls/sources/inbox 摘要、驱动发送循环 |
| `useQuickChat` | [`useQuickChat.ts:13-33`](../../frontend/src/hooks/useQuickChat.ts) | 创建会话、导航到 `/chat/{id}`、可选设 pending prompt |
| `useApprovalFlow` | [`useApprovalFlow.ts:37-231`](../../frontend/src/hooks/useApprovalFlow.ts) | 管理待工具确认；会话级 trusted-tools 缓存（`sessionStorage["par_trust_session_{convId}"]`）；inflight 审批去重；trusted 工具自动批准 |
| `useNotifications` | [`useNotifications.ts:49-141`](../../frontend/src/hooks/useNotifications.ts) | 持有 WebSocket（最多 5 次重连，5s 退避）；toast + 实时通知；每 payload 转发到失效桥 |
| `useWsInvalidationBridge` | [`useWsInvalidationBridge.ts`](../../frontend/src/hooks/useWsInvalidationBridge.ts) | 见上 |
| `useDashboard` | [`useDashboard.ts`](../../frontend/src/hooks/useDashboard.ts) | 见上 |
| `useMemoriesGroupedQuery` | [`useMemoriesQuery.ts`](../../frontend/src/hooks/useMemoriesQuery.ts) | 见上 |

## 组件

[`frontend/src/components/`](../../frontend/src/components/)：

- **`ui/`** — 原语：`Button`、`Badge`、`Card`、`Dialog`、`EmptyState`、`ErrorBoundary`、`Input`（含 `PasswordInput`）、`Spinner`。每个有 co-located `.test.tsx`。
- **`layout/`** — `Sidebar.tsx`（聊天列表 + 导航，[`Sidebar.tsx:22-37`](../../frontend/src/components/layout/Sidebar.tsx)）、`NotificationBell.tsx`。
- **`chat/`** — `ChatView.tsx`（活跃会话）、`ChatHome.tsx`（落地）、`MessageItem.tsx`、`ToolCallDisplay.tsx`、`ContextPanel.tsx`、`ConfirmationDialog.tsx`（审批模态）、`VoiceInput.tsx`、`CodeBlock.tsx`（懒加载 `react-syntax-highlighter`）。
- **`notifications/`** — `NotificationDetailModal.tsx`。
- **`onboarding/`** — `OnboardingWizard.tsx`（首次运行，`localStorage.onboarding_done` 门控）。

侧栏导航模型（[`Sidebar.tsx:22-37`](../../frontend/src/components/layout/Sidebar.tsx)）：

- `PRIMARY_NAV`：`/`「对话」
- `DATA_NAV`（折叠在「我的数据」组下）：`/portrait`「画像」、`/trust`「信任报告」、`/demo`「模型切换 Demo」、`/goals`「目标」、`/inbox`「收件箱」、`/approvals`「审批」、`/memories`「记忆」、`/timeline`「时间线」、`/knowledge`「知识库」、`/dashboard`「仪表盘」
- `SYSTEM_NAV`：`/settings`「设置」

会话列表只在 chat 路由显示。

## Layout

[`frontend/src/Layout.tsx`](../../frontend/src/Layout.tsx) 渲染：

1. `<Sidebar>`（左 256px）含会话列表 + 导航。
2. Banner 覆盖层：(a) 后端需认证但未配 token，(b) 后端不可用。
3. Toast 栈（右上）：WS 实时通知 + `useErrorStore` 错误 toast。
4. `<main>` 含 `<Suspense>` + `<ErrorBoundary>` 包 `<Outlet />`。
5. 对话框：删除会话确认、`OnboardingWizard`、`NotificationDetailModal`。

Layout 在根处挂三个副作用 hook：`useNotifications()`（持有 WS）、`useWsInvalidationBridge()`、挂载时调 `getSystemHealth()` + `listConversations()`。

## 构建 / 开发 / 测试

### Scripts（[`frontend/package.json:6-14`](../../frontend/package.json)）

| Script | 命令 |
|---|---|
| `dev` | `vite` |
| `build` | `tsc -b && vite build` |
| `preview` | `vite preview` |
| `test` | `vitest run` |
| `test:e2e` | `playwright test` |
| `lint` | `eslint src/ && prettier --check src/` |
| `format` | `prettier --write src/` |

### Vite 配置

[`frontend/vite.config.ts`](../../frontend/vite.config.ts)：

- 插件：`@vitejs/plugin-react`、`@tailwindcss/vite`。
- `envDir: rootDir` — 仓库根 `.env` 是 `VITE_API_HOST`/`VITE_API_PORT`/`VITE_AUTH_TOKEN` 源。
- Dev server 端口 5173；proxy `/api` 与 `/ws`（`ws: true`）。
- `define`：`__API_HOST__`、`__API_PORT__`（声明于 [`vite-env.d.ts:11-12`](../../frontend/src/vite-env.d.ts)）。
- 生产 `manualChunks`：分离 `vendor-markdown`、`vendor-react`、`vendor-icons`、通用 `vendor`、每页 chunk（`page-{name}`）。

### TypeScript

[`frontend/tsconfig.json`](../../frontend/tsconfig.json)：ES2020、bundler 解析、`jsx: react-jsx`、strict、`noEmit`、`forceConsistentCasingInFileNames`。`noUnusedLocals/Parameters` **关闭**。

### ESLint

[`frontend/eslint.config.js`](../../frontend/eslint.config.js)：Flat config，`@eslint/js` recommended + `typescript-eslint` recommended。忽略 `dist/`、`node_modules/`、`test-results/`。自定义：`no-unused-vars` warn（`_` 参量忽略）、`no-explicit-any` warn。

### Vitest

[`frontend/vitest.config.ts`](../../frontend/vitest.config.ts)：jsdom、包含 `src/**/*.test.{ts,tsx}`、setup 文件 [`src/test/setup.ts`](../../frontend/src/test/setup.ts)（注册 `@testing-library/jest-dom` + 每测 cleanup）。定义 `__API_HOST__`/`__API_PORT__`。

### Playwright

[`frontend/playwright.config.ts`](../../frontend/playwright.config.ts)：`testDir: "./e2e"`、60s 超时、headless、baseURL `http://localhost:5173`。`webServer.command: "npm run dev"`，复用已存在 server，120s 超时。

唯一 e2e 文件：[`e2e/chat-approval.spec.ts`](../../frontend/e2e/chat-approval.spec.ts)，配合 [`e2e/helpers.ts`](../../frontend/e2e/helpers.ts) 的 `MockApiRouter`。覆盖导航、聊天发送、审批确认/拒绝流、仪表盘错误态、时间线/知识页、仪表盘数据主权面板——全部用 mock router。

### 单元测试

- Vitest：`auth.test.ts`、`api/client.test.ts`，组件测试 `Button/Input/Dialog/Sidebar/MessageItem/ToolCallDisplay/ContextPanel/ConfirmationDialog/ChatView/ui.snapshots`，页面测试 `Dashboard/Inbox/Memories/Goals/Settings/Portrait/TrustReport`。strip/tool-label 工具也有测试。

## 工具

[`frontend/src/utils/`](../../frontend/src/utils/)：

- `stripToolMarkup.ts` — 去除助手文本中的内联工具调用标记（带测试）。
- `timeUtils.ts` — `timeAgo`、`isStagnant`（Goals 用）。
- `toolLabels.ts` / `toolLabels.test.ts` — 工具名友好中文标签。
- `notificationRoutes.ts` — 通知类型 → 路由 + 标签。
- `notificationUtils.ts` — `notificationPreview`（截断）。
