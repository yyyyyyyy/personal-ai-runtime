import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getSystemHealth, isAuthConfigured, setAuthToken } from "./client";

describe("api client auth", () => {
  beforeEach(() => {
    setAuthToken("");
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("setAuthToken adds Authorization header to requests", async () => {
    setAuthToken("secret-token");
    expect(isAuthConfigured()).toBe(true);

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok", auth_required: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await getSystemHealth();

    expect(fetch).toHaveBeenCalledWith(
      "/api/system/health",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer secret-token",
        }),
      }),
    );
  });

  it("throws ApiError on 401", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 }),
    );

    const err = await getSystemHealth().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 401 });
  });
});
