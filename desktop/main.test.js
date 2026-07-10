/**
 * Smoke test for Electron main process.
 *
 * Verifies that main.js can be parsed without syntax errors
 * and that key configuration constants are valid.
 *
 * Does NOT require Electron to be installed — validates code structure only.
 */

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const mainJsPath = join(__dirname, "main.js");

describe("Electron main process", () => {
  let source;

  beforeAll(() => {
    source = readFileSync(mainJsPath, "utf-8");
  });

  it("is valid JavaScript with no syntax errors", () => {
    // Attempt to parse as a module — syntax errors will throw
    expect(() => {
      new Function(source);
    }).not.toThrow();
  });

  it("defines WEB_URL constant", () => {
    expect(source).toContain("WEB_URL");
  });

  it("defines BACKEND_URL constant", () => {
    expect(source).toContain("BACKEND_URL");
  });

  it("defines AUTH_TOKEN constant", () => {
    expect(source).toContain("AUTH_TOKEN");
  });

  it("has a createMainWindow function", () => {
    expect(source).toContain("function createMainWindow");
  });

  it("has a createTray function", () => {
    expect(source).toContain("function createTray");
  });

  it("has a connectWebSocket function for notifications", () => {
    expect(source).toContain("function connectWebSocket");
  });

  it("registers global shortcuts", () => {
    expect(source).toContain("globalShortcut.register");
  });

  it("handles IPC for get-backend-url", () => {
    expect(source).toContain("get-backend-url");
  });

  it("handles IPC for send-notification", () => {
    expect(source).toContain("send-notification");
  });

  it("sets login item settings for auto-start", () => {
    expect(source).toContain("setLoginItemSettings");
  });

  it("registers a privileged app:// scheme for production", () => {
    expect(source).toContain("registerSchemesAsPrivileged");
    expect(source).toContain("scheme: \"app\"");
  });

  it("has a registerAppProtocol function for serving frontend-dist", () => {
    expect(source).toContain("function registerAppProtocol");
    expect(source).toContain("protocol.handle");
  });

  it("installs an API proxy for /api and /ws in production", () => {
    expect(source).toContain("function installApiProxy");
    expect(source).toContain("webRequest.onBeforeRequest");
  });

  it("resolves web URL differently for packaged vs dev", () => {
    expect(source).toContain("isPackaged");
    expect(source).toContain("function resolveWebUrl");
    expect(source).toContain("app://./");
  });

  it("resolves backend dir from extraResources when packaged", () => {
    expect(source).toContain("function resolveBackendDir");
    expect(source).toContain("process.resourcesPath");
  });

  it("resolves python command for platform and bundled runtime", () => {
    expect(source).toContain("function resolvePythonCommand");
    expect(source).toContain("resolveBundledPythonExe");
  });

  it("uses a backend launcher for embeddable Python sys.path", () => {
    expect(source).toContain("run-backend.py");
    expect(source).toContain("BACKEND_DIR");
    expect(source).toContain("waitForBackendReady");
  });

  it("redirects desktop data to userData", () => {
    expect(source).toContain("function resolveDesktopDataEnv");
    expect(source).toContain("DATA_DIR");
  });
});
