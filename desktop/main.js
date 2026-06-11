/**
 * Electron main process for Personal AI Runtime Desktop.
 *
 * Provides:
 * - System tray icon with quick actions
 * - Global shortcut (Alt+Space) for quick chat
 * - Quick capture (Alt+Shift+I) for Inbox
 * - Native notifications
 * - Auto-start on login
 * - Loads the web app in a frameless window
 */

const { app, BrowserWindow, Tray, Menu, globalShortcut, Notification, dialog } = require('electron');
const path = require('path');

// Configuration
const WEB_URL = process.env.WEB_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

let mainWindow = null;
let miniWindow = null;
let tray = null;
let isQuitting = false;

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'Personal AI Runtime',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    frame: true,
    show: false,
  });

  mainWindow.loadURL(WEB_URL);

  mainWindow.on('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
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
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  miniWindow.loadURL(WEB_URL);

  miniWindow.on('blur', () => {
    if (miniWindow) {
      miniWindow.close();
      miniWindow = null;
    }
  });

  miniWindow.on('closed', () => {
    miniWindow = null;
  });
}

function createTray() {
  // Create a simple 16x16 tray icon using nativeImage
  const { nativeImage } = require('electron');
  // Create a colored square as icon
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '打开 Personal AI Runtime',
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
      label: '快捷对话 (Alt+Space)',
      click: () => createMiniWindow(),
    },
    { type: 'separator' },
    {
      label: '关于',
      click: () => {
        dialog.showMessageBox({
          type: 'info',
          title: 'Personal AI Runtime',
          message: 'Personal AI Runtime v0.7.0',
          detail: '你的第二大脑和执行引擎',
        });
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setToolTip('Personal AI Runtime');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });
}

function registerGlobalShortcuts() {
  // Alt+Space: Quick chat window
  globalShortcut.register('Alt+Space', () => {
    createMiniWindow();
  });

  // Alt+Shift+I: Quick capture Inbox
  globalShortcut.register('Alt+Shift+I', () => {
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

  // Send a message to quickly capture
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
    notification.on('click', () => {
      if (mainWindow) {
        mainWindow.show();
        mainWindow.focus();
      } else {
        createMainWindow();
      }
    });
  }
}

// App lifecycle
app.whenReady().then(() => {
  createMainWindow();
  createTray();
  registerGlobalShortcuts();

  // Connect to WebSocket for notifications
  connectWebSocket();

  app.on('activate', () => {
    if (mainWindow === null) {
      createMainWindow();
    } else {
      mainWindow.show();
    }
  });
});

app.on('window-all-closed', () => {
  if (!isQuitting) {
    // Do nothing, keep running in tray
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  globalShortcut.unregisterAll();
});

// Auto-start on login
app.setLoginItemSettings({
  openAtLogin: true,
  openAsHidden: true,
});

// WebSocket connection for real-time notifications
function connectWebSocket() {
  try {
    const WebSocket = require('ws');
    const ws = new WebSocket(`ws://localhost:8000/ws`);

    ws.on('open', () => {
      console.log('WebSocket connected for notifications');
    });

    ws.on('message', (data) => {
      try {
        const event = JSON.parse(data.toString());
        if (event.type === 'notification') {
          showNotification(event.title, event.content);
        }
      } catch (e) {
        // Ignore parse errors
      }
    });

    ws.on('close', () => {
      // Reconnect after 5 seconds
      setTimeout(connectWebSocket, 5000);
    });

    ws.on('error', () => {
      // Retry later
      setTimeout(connectWebSocket, 10000);
    });
  } catch (e) {
    // WebSocket not available, skip
  }
}

// Expose IPC handlers
const { ipcMain } = require('electron');

ipcMain.handle('get-backend-url', () => BACKEND_URL);

ipcMain.handle('send-notification', (event, { title, body }) => {
  showNotification(title, body);
});
