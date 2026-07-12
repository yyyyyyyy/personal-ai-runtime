/**
 * Preload script for Personal AI Runtime Desktop.
 *
 * The renderer (loaded via app:// or http) talks to the backend directly over
 * HTTP/SSE/WebSocket. No privileged IPC bridge is exposed to the renderer.
 *
 * Desktop-native concerns (system notifications on WebSocket events, tray,
 * global shortcuts) are handled entirely in the main process (see main.js).
 */
