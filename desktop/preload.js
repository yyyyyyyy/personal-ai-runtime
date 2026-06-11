/**
 * Preload script for Personal AI Runtime Desktop.
 * Exposes safe IPC methods to the renderer process.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  sendNotification: (title, body) => ipcRenderer.invoke('send-notification', { title, body }),
  platform: process.platform,
});
