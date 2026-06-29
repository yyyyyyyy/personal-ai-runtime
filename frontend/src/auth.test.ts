import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("auth initialization", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("loads token from VITE_AUTH_TOKEN", async () => {
    vi.stubEnv("VITE_AUTH_TOKEN", "env-token");
    await import("./auth");
    const { getAuthToken } = await import("./api/client");
    expect(getAuthToken()).toBe("env-token");
  });

  it("saveAuthToken persists to localStorage", async () => {
    const { saveAuthToken } = await import("./auth");
    const { getAuthToken, isAuthConfigured } = await import("./api/client");

    saveAuthToken("stored-token");
    expect(isAuthConfigured()).toBe(true);
    expect(getAuthToken()).toBe("stored-token");
    expect(localStorage.getItem("auth_token")).toBe("stored-token");
  });
});
