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
});
