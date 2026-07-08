/**
 * Electron main process for Personal AI Runtime Desktop.
 *
 * Provides:
 * - System tray icon with quick actions
 * - Global shortcut (Alt+Space) for quick chat
 * - Quick capture (Alt+Shift+I) for Inbox
 * - Native notifications
 * - Auto-start on login
 * - Backend process management (auto-start/stop)
 * - Loads the web app in a frameless window
 */

const { app, BrowserWindow, Tray, Menu, globalShortcut, Notification, dialog, nativeImage, protocol, session } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const net = require("net");

// Declare the app:// scheme as privileged BEFORE app is ready.
// This must happen synchronously at module load time so the renderer can use
// fetch, cookies, service workers, and relative URLs under app://
protocol.registerSchemesAsPrivileged([
  {
    scheme: "app",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
      bypassCSP: false,
      codeCache: true,
    },
  },
]);

// ── Configuration ────────────────────────────────────────────────────

const WEB_URL = process.env.WEB_URL || "";
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const BACKEND_PORT = new URL(BACKEND_URL).port || "8000";
const AUTH_TOKEN = process.env.AUTH_TOKEN || "";

// Production: app.isPackaged is true for electron-builder output.
// In production we load the bundled frontend-dist/index.html via a custom
// `app://` protocol (registered in registerAppProtocol) and proxy /api + /ws
// to the local backend via session.webRequest. In dev we use the Vite dev
// server (http://localhost:5173) which already proxies /api and /ws.
const isPackaged = app.isPackaged;

// Resolve the frontend entry: app:// protocol in production, dev server otherwise.
// WEB_URL env var always wins (lets dev override).
function resolveWebUrl() {
  if (WEB_URL) return WEB_URL;
  if (isPackaged) {
    const distDir = path.join(__dirname, "frontend-dist");
    if (fs.existsSync(path.join(distDir, "index.html"))) {
      return "app://./index.html";
    }
    console.warn("[desktop] Packaged but frontend-dist/index.html missing, falling back to dev URL.");
  }
  return "http://localhost:5173";
}

// Resolve backend working directory.
function resolveBackendDir() {
  if (isPackaged) {
    return path.join(process.resourcesPath, "backend");
  }
  return path.join(__dirname, "..", "backend");
}

function readAppVersion() {
  try {
    const versionPath = path.join(__dirname, "..", "VERSION");
    return fs.readFileSync(versionPath, "utf8").trim();
  } catch {
    return "0.2.0";
  }
}

const APP_VERSION = readAppVersion();
const RESOLVED_WEB_URL = resolveWebUrl();
const RESOLVED_BACKEND_DIR = resolveBackendDir();

// ── Custom protocol + request proxying (production only) ─────────────
//
// In production the renderer loads `app://./index.html`. The `app://` scheme
// serves files from frontend-dist/. API calls to `/api/*` and WebSocket
// upgrades to `/ws` are rewritten to the local backend via webRequest so the
// frontend's relative API_BASE ("/api") works unchanged.

let _appProtocolRegistered = false;

function registerAppProtocol() {
  if (_appProtocolRegistered || !isPackaged) return;

  const distRoot = path.join(__dirname, "frontend-dist");
  protocol.handle("app", (request) => {
    const url = new URL(request.url);
    // url.hostname is "." for app://./path ; url.pathname is the file path.
    let relPath = decodeURIComponent(url.pathname);
    if (relPath.startsWith("/")) relPath = relPath.slice(1);
    let filePath = path.join(distRoot, relPath);
    // SPA fallback: non-existent paths serve index.html (except /assets/*)
    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      filePath = path.join(distRoot, "index.html");
    }
    return net.fetch(`file://${filePath}`);
  });
  _appProtocolRegistered = true;
}

function installApiProxy() {
  if (!isPackaged) return;
  const backendOrigin = `http://127.0.0.1:${BACKEND_PORT}`;
  const ses = session.defaultSession;

  ses.webRequest.onBeforeRequest({ urls: ["http://localhost/api/*", "http://127.0.0.1/api/*"] }, (details, callback) => {
    callback({ redirectURL: `${backendOrigin}${details.url.slice(details.url.indexOf("/api"))}` });
  });

  // /ws upgrade redirect
  ses.webRequest.onBeforeRequest({ urls: ["ws://localhost/ws*", "ws://127.0.0.1/ws*"] }, (details, callback) => {
    const wsOrigin = `ws://127.0.0.1:${BACKEND_PORT}`;
    callback({ redirectURL: `${wsOrigin}${details.url.slice(details.url.indexOf("/ws"))}` });
  });
}

// ── Backend Process Management ───────────────────────────────────────

let backendProcess = null;
let backendStarting = false;

function startBackend() {
  if (backendProcess || backendStarting) return;

  backendStarting = true;
  const backendDir = RESOLVED_BACKEND_DIR;

  // Check if backend is already running
  const net = require("net");
  const client = new net.Socket();
  client.connect(parseInt(BACKEND_PORT), "localhost", () => {
    client.destroy();
    console.log("Backend already running on port", BACKEND_PORT);
    backendStarting = false;
  });

  client.on("error", () => {
    client.destroy();
    console.log("Starting backend...");

    backendProcess = spawn("python3", ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", BACKEND_PORT], {
      cwd: backendDir,
      env: { ...process.env },
      stdio: ["ignore", "pipe", "pipe"],
    });

    backendProcess.stdout.on("data", (data) => {
      console.log("[backend]", data.toString().trim());
    });

    backendProcess.stderr.on("data", (data) => {
      console.log("[backend]", data.toString().trim());
    });

    backendProcess.on("close", (code) => {
      console.log("Backend exited with code", code);
      backendProcess = null;
    });

    backendProcess.on("error", (err) => {
      console.error("Backend start error:", err.message);
      backendProcess = null;
    });

    backendStarting = false;
  });
}

function stopBackend() {
  if (backendProcess) {
    console.log("Stopping backend...");
    backendProcess.kill("SIGTERM");
    setTimeout(() => {
      if (backendProcess) {
        backendProcess.kill("SIGKILL");
        backendProcess = null;
      }
    }, 5000);
  }
}

// ── Window State ─────────────────────────────────────────────────────

let mainWindow = null;
let miniWindow = null;
let tray = null;
let isQuitting = false;

function createTrayIcon() {
  // Use the generated icon.png if available, otherwise fall back to a colored square
  const iconPath = path.join(__dirname, "icon.png");
  let trayIcon;
  try {
    if (fs.existsSync(iconPath)) {
      trayIcon = nativeImage.createFromPath(iconPath);
      // macOS tray icons should be small
      if (process.platform === "darwin") {
        trayIcon = trayIcon.resize({ width: 16, height: 16 });
      }
    } else {
      trayIcon = createFallbackIcon();
    }
  } catch {
    trayIcon = createFallbackIcon();
  }
  return trayIcon;
}

function createFallbackIcon() {
  // Fallback: empty 16x16 icon (icon.png should be generated by postinstall script)
  return nativeImage.createEmpty();
}

function createMainWindow() {
  const iconPath = path.join(__dirname, "icon.png");
  const winOpts = {
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: "Personal AI Runtime",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
    frame: true,
    show: false,
  };
  if (fs.existsSync(iconPath)) {
    winOpts.icon = iconPath;
  }

  mainWindow = new BrowserWindow(winOpts);
  mainWindow.loadURL(RESOLVED_WEB_URL);

  mainWindow.on("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function createMiniWindow() {
  if (miniWindow) {
    miniWindow.focus();
    return;
  }

  miniWindow = new BrowserWindow({
    width: 600,
    height: 500,
    resizable: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  miniWindow.loadURL(RESOLVED_WEB_URL);

  miniWindow.on("blur", () => {
    if (miniWindow) {
      miniWindow.close();
      miniWindow = null;
    }
  });

  miniWindow.on("closed", () => {
    miniWindow = null;
  });
}

function createTray() {
  tray = new Tray(createTrayIcon());

  const contextMenu = Menu.buildFromTemplate(createTrayMenuItems());

  tray.setToolTip("Personal AI Runtime");
  tray.setContextMenu(contextMenu);

  // Rebuild menu on click to reflect toggle state
  tray.on("click", () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
    tray.setContextMenu(Menu.buildFromTemplate(createTrayMenuItems()));
  });
  tray.on("right-click", () => {
    tray.setContextMenu(Menu.buildFromTemplate(createTrayMenuItems()));
  });
}

function createTrayMenuItems() {
  const autoLaunchEnabled = app.getLoginItemSettings().openAtLogin;
  return [
    {
      label: "打开 Personal AI Runtime",
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        } else {
          createMainWindow();
        }
      },
    },
    {
      label: "快捷对话 (Alt+Space)",
      click: () => createMiniWindow(),
    },
    { type: "separator" },
    {
      label: backendProcess ? "重启后端" : "启动后端",
      click: () => {
        stopBackend();
        setTimeout(startBackend, 1000);
      },
    },
    { type: "separator" },
    {
      label: autoLaunchEnabled ? "✓ 开机自启" : "开机自启",
      type: "checkbox",
      checked: autoLaunchEnabled,
      click: (menuItem) => {
        app.setLoginItemSettings({
          openAtLogin: menuItem.checked,
          openAsHidden: true,
        });
      },
    },
    { type: "separator" },
    {
      label: "关于",
      click: () => {
        const statusText = backendProcess ? "后端运行中" : "后端未运行（需手动启动 backend）";
        dialog.showMessageBox({
          type: "info",
          title: "Personal AI Runtime",
          message: `Personal AI Runtime v${APP_VERSION}`,
          detail: `${statusText}\n数据存于本机，完全私有`,
        });
      },
    },
    { type: "separator" },
    {
      label: "退出",
      click: () => {
        isQuitting = true;
        stopBackend();
        app.quit();
      },
    },
  ];
}

function registerGlobalShortcuts() {
  globalShortcut.register("Alt+Space", () => {
    createMiniWindow();
  });

  globalShortcut.register("Alt+Shift+I", () => {
    quickCapture();
  });
}

async function quickCapture() {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
  } else {
    createMainWindow();
  }
  if (mainWindow) {
    mainWindow.webContents.executeJavaScript(`
      window.postMessage({ type: 'quick-capture' }, '*');
    `);
  }
}

function showNotification(title, body) {
  if (Notification.isSupported()) {
    const notification = new Notification({ title, body });
    notification.show();
    notification.on("click", () => {
      if (mainWindow) {
        mainWindow.show();
        mainWindow.focus();
      } else {
        createMainWindow();
      }
    });
  }
}

// ── App Lifecycle ────────────────────────────────────────────────────

app.whenReady().then(async () => {
  // Register custom protocol + API proxy before any window is created.
  registerAppProtocol();
  installApiProxy();

  // First-run: ask for auto-launch consent (was previously forced).
  try {
    const settings = app.getLoginItemSettings();
    if (!settings.openAtLogin && !settings.wasOpenedAtLogin) {
      const result = await dialog.showMessageBox({
        type: "question",
        title: "Personal AI Runtime",
        message: "是否允许开机自启？",
        detail: "开机自启后，AI 可以在后台持续为你工作。你可以在托盘菜单中随时切换。",
        buttons: ["允许", "暂不"],
        defaultId: 0,
        cancelId: 1,
      });
      if (result.response === 0) {
        app.setLoginItemSettings({ openAtLogin: true, openAsHidden: true });
      }
    }
  } catch {
    // login item settings not supported on this platform — skip silently
  }

  // Auto-start backend
  startBackend();

  createMainWindow();
  createTray();
  registerGlobalShortcuts();
  connectWebSocket();

  app.on("activate", () => {
    if (mainWindow === null) {
      createMainWindow();
    } else {
      mainWindow.show();
    }
  });
});

app.on("window-all-closed", () => {
  // Keep running in tray
});

app.on("before-quit", () => {
  isQuitting = true;
  globalShortcut.unregisterAll();
  stopBackend();
});

// Check if auto-launch was previously consented; if not, ask on first run.
const launchKey = "autoLaunchAccepted";
try {
  const launchAccepted = app.getLoginItemSettings().openAtLogin;
  if (!launchAccepted) {
    // Will be prompted below (after app ready)
  }
} catch {
  // ignore — platform may not support login items
}

// ── WebSocket ────────────────────────────────────────────────────────

function connectWebSocket() {
  try {
    const WebSocket = require("ws");
    const wsUrl = BACKEND_URL.replace(/^http/, "ws") + "/ws";
    const protocols = AUTH_TOKEN ? [`auth.${AUTH_TOKEN}`, "auth.ok"] : undefined;
    const ws = protocols ? new WebSocket(wsUrl, protocols) : new WebSocket(wsUrl);

    ws.on("open", () => {
      console.log("WebSocket connected for notifications");
    });

    ws.on("message", (data) => {
      try {
        const event = JSON.parse(data.toString());
        if (event.type === "notification") {
          showNotification(event.title, event.content);
        }
      } catch {
        // Ignore parse errors
      }
    });

    ws.on("close", () => {
      setTimeout(connectWebSocket, 5000);
    });

    ws.on("error", () => {
      setTimeout(connectWebSocket, 10000);
    });
  } catch {
    // WebSocket not available, skip
  }
}

// ── IPC ──────────────────────────────────────────────────────────────

const { ipcMain } = require("electron");

ipcMain.handle("get-backend-url", () => BACKEND_URL);

ipcMain.handle("send-notification", (_event, { title, body }) => {
  showNotification(title, body);
});
