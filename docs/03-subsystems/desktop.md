# 桌面端子系统

本文档描述 Electron 包装（`desktop/`）。它 spawn Python 后端子进程、加载前端 dev URL、提供托盘与全局快捷键。

## 角色

桌面端是一个**薄 Electron 包装**，做四件事：

1. spawn 并监管 Python 后端（`uvicorn app.main:app`）作为子进程。
2. 在 `BrowserWindow` 加载前端（默认 Vite dev server URL）。
3. 添加系统托盘、全局快捷键、原生通知、开机自启。
4. 维护后端 WebSocket 连接以接收桌面通知。

## 关键文件

| 文件 | 行数 | 职责 |
|---|---|---|
| [`desktop/main.js`](../../desktop/main.js) | 704 | 主进程 |
| [`desktop/preload.js`](../../desktop/preload.js) | 9 | preload（无 IPC 暴露） |
| [`desktop/main.test.js`](../../desktop/main.test.js) | 105 | vitest smoke 测试 |
| [`desktop/package.json`](../../desktop/package.json) | — | scripts + electron-builder 配置 |
| [`desktop/vitest.config.js`](../../desktop/vitest.config.js) | — | vitest 配置 |
| [`desktop/generate_icon.py`](../../desktop/generate_icon.py) | — | `postinstall` 时生成 `icon.png` |

## 配置

[`main.js:37-84`](../../desktop/main.js)：

```
WEB_URL      = process.env.WEB_URL      || ""    # 空则自动解析
BACKEND_URL  = process.env.BACKEND_URL  || "http://localhost:8000"
BACKEND_PORT = new URL(BACKEND_URL).port || "8000"
AUTH_TOKEN   = process.env.AUTH_TOKEN   || ""
```

`resolveWebUrl()` 按 `app.isPackaged` 分流：

- **打包发行**：注册自定义 `app://` 协议服务 `frontend-dist/`，主窗口加载 `app://./index.html`；`/api/*` 与 `/ws` 通过 `session.webRequest` 转发到本地后端。
- **开发**：回退到 Vite dev server `http://localhost:5173`（其 vite proxy 已转发 `/api`、`/ws`）。
- `WEB_URL` 环境变量总是最高优先级（允许手动覆盖）。

`resolveBackendDir()` 按打包状态分流：打包时指向 `process.resourcesPath/backend`（extraResources），开发时指向 `<repo>/backend`。`readAppVersion()` 读 `../VERSION`，缺失回退 `"0.2.0"`。

## 后端进程管理

**Python 运行时**（v0.5.1 起）：

- **Windows 打包版**：`prebuild.js` 通过 [`bundle-python.js`](../../desktop/bundle-python.js) 捆绑 embeddable CPython 3.12 + `requirements.txt` 到 `extraResources/python/`；`main.js` 优先使用捆绑的 `python.exe`。
- **开发 / 非 Windows**：`resolvePythonCommand()` 依次尝试 `py -3.12`、`python`、`python3`；依赖系统已安装的后端包。
- **数据目录**：spawn 时注入 `DATA_DIR` / `VECTOR_DIR` / `SQLITE_PATH` 到 `%APPDATA%/Personal AI Runtime/data`（`app.getPath("userData")`），避免写入只读安装目录。
- **依赖探测**：启动前执行 `import uvicorn, chromadb`；失败时弹出 `dialog.showErrorBox` 并指引运行 [`install.bat`](../../install.bat)（Windows）或 `install.sh`。

[`main.js`](../../desktop/main.js) 的 `startBackend()`：

1. 探测 `BACKEND_PORT`：用 `net.Socket` 连 localhost。
2. 若已有进程监听 → 复用，记日志。
3. 若连不上 → 解析 Python 可执行文件并 spawn：

```
<python> -m uvicorn app.main:app --host 127.0.0.1 --port <BACKEND_PORT>
cwd = <repo>/backend  (或 resources/backend)
env = { ...process.env, DATA_DIR, VECTOR_DIR, SQLITE_PATH }
stdio = ["ignore", "pipe", "pipe"]
```

托盘菜单提供「重启后端」/「启动后端」；`stopBackend()` 发 SIGTERM（5s 后升级为 SIGKILL）。

## 窗口管理

- `createMainWindow()`（[`main.js:135-172`](../../desktop/main.js)）：1200×800，最小 800×600，`nodeIntegration: false`、`contextIsolation: true`、`preload: preload.js`、`frame: true`，`ready-to-show` 前隐藏。关闭 → 隐藏（驻留托盘），除非正在退出。
- `createMiniWindow()`（[`main.js:174-206`](../../desktop/main.js)）：600×500 无边框、置顶、跳过任务栏的「快捷对话」弹窗（Alt+Space），失焦关闭。

## 系统托盘

`createTray()`（[`main.js:208-290`](../../desktop/main.js)）：图标来自 `desktop/icon.png`（缺失回退空 16×16）；上下文菜单：打开 / 快捷对话（Alt+Space）/ 重启或启动后端 / 开机自启（复选框）/ 关于 / 退出。

## 全局快捷键

`registerGlobalShortcuts()`（[`main.js:292-300`](../../desktop/main.js)）：

- `Alt+Space` → 打开 mini window。
- `Alt+Shift+I` → `quickCapture()`：显示主窗口并 `postMessage({ type: 'quick-capture' })` 到 renderer。

## 原生通知

`showNotification()`（[`main.js:316-329`](../../desktop/main.js)）：用 Electron `Notification`；点击把主窗口带到前台。

## 应用生命周期

[`main.js:333-380`](../../desktop/main.js)：`whenReady` 时提示开机自启同意（首次运行），然后 `startBackend()` + `createMainWindow()` + `createTray()` + `registerGlobalShortcuts()` + `connectWebSocket()`。`window-all-closed` 是 no-op（驻留托盘）。`before-quit` 注销快捷键并停后端。

## WebSocket

`connectWebSocket()`（[`desktop/main.js`](../../desktop/main.js)）：用 `ws` 包，连接 `BACKEND_URL.replace(/^http/,'ws') + "/ws"`。若 `AUTH_TOKEN` 设置，用子协议 `[`auth.${AUTH_TOKEN}`, "auth.ok"]`。监听 `{type:"notification"}` payload 并调 `showNotification`。关闭 5s / 错误 10s 自动重连。

## Preload / IPC

[`desktop/preload.js`](../../desktop/preload.js) 不向渲染进程暴露任何 IPC 绑定；main 进程亦无 `ipcMain.handle` 面向渲染器的通道。渲染进程（前端 SPA）通过 HTTP/SSE/WebSocket 直连后端。桌面原生行为（托盘、全局快捷键、WebSocket→系统通知）由 main 进程处理（见上节 WebSocket）。

> 历史：早期版本通过 `contextBridge.exposeInMainWorld('electronAPI', ...)` 暴露 `getBackendUrl`/`sendNotification`/`platform`，并有对应 `ipcMain.handle`；`frontend/src/` 中无消费方，已移除以收窄 Electron 可信边界。

## Smoke 测试

[`desktop/main.test.js`](../../desktop/main.test.js) 是 vitest smoke 测试，**不需要 Electron 已安装**。它读 `main.js` 源码（字符串 `toContain`）断言：

- 源码作为有效 JS 解析（`new Function(source)`）。
- 常量 `WEB_URL`、`BACKEND_URL`、`AUTH_TOKEN` 存在。
- 函数 `createMainWindow`、`createTray`、`connectWebSocket` 存在。
- 调用 `globalShortcut.register`、`setLoginItemSettings`。

## 构建配置

[`desktop/package.json`](../../desktop/package.json)：

| Script | 命令 | 说明 |
|---|---|---|
| `start` | `electron .` | 开发模式启动 |
| `prebuild` | `node prebuild.js` | 构建/复制 frontend dist 到 `desktop/frontend-dist/` |
| `build` | `npm run prebuild && electron-builder` | 先打前端再打桌面包 |
| `test` | `vitest run --config vitest.config.js` | smoke 测试 |
| `postinstall` | `python3 generate_icon.py` | 生成图标 |

[`desktop/prebuild.js`](../../desktop/prebuild.js)：检测 `frontend/dist` 是否新鲜，缺失则 `npm ci && npm run build`，然后递归复制到 `desktop/frontend-dist/`。该目录被 `.gitignore` 忽略（构建产物）。

electron-builder 配置：

- `appId: com.personalairuntime.desktop`、`productName: Personal AI Runtime`。
- `files`：`main.js`、`preload.js`、`icon.png`、`generate_icon.py`、`frontend-dist/**/*`。
- `extraResources`：把整个 `../backend` 目录 bundle 为 `backend`（排除 `__pycache__`、`*.pyc`、`data/**`）。所以打包发行版**包含 Python 源码 + 前端构建产物**，但运行时仍需系统 Python 3。
- Targets：macOS（`dmg`、`zip`）、Windows（`nsis`、`portable`）、Linux（`AppImage`、`deb`）。
- `desktop/vitest.config.js` — `globals: true`，包含 `**/*.test.js`。

## 自定义协议与 API 代理（生产模式）

生产模式下 `registerAppProtocol()`（[`main.js:95-112`](../../desktop/main.js)）注册 `app://` scheme（通过 `registerSchemesAsPrivileged` 声明为 standard/secure/supportFetchAPI/stream）。`protocol.handle("app", ...)` 把请求映射到 `frontend-dist/` 下的文件，对不存在路径做 SPA fallback（返回 `index.html`）。

`installApiProxy()`（[`main.js:114-130`](../../desktop/main.js)）用 `session.defaultSession.webRequest.onBeforeRequest` 把 `/api/*` 和 `/ws*` 重定向到 `http://127.0.0.1:<BACKEND_PORT>`，使前端相对路径 `API_BASE="/api"` 无需修改即可工作。

## 运行模式总结

| 场景 | 行为 |
|---|---|
| 开发（`make dev` + `make desktop`） | uvicorn 与 vite 各自前台运行；Electron 加载 `http://localhost:5173`，探测到 8000 端口已有后端则复用；`app://` 协议与 webRequest 代理不启用 |
| 打包发行（`npm run build`） | `prebuild.js` 构建前端并复制到 `desktop/frontend-dist/`；electron-builder 把 backend 源码 + frontend-dist 一起打入；运行时 Electron 注册 `app://` 协议服务前端，spawn 系统 python3 跑后端，`/api` 与 `/ws` 经 webRequest 转发；**离线可用** |
