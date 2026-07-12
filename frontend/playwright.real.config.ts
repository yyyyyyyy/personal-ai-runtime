import { defineConfig } from "@playwright/test";

/** Real-backend E2E config — starts backend + fake LLM in beforeAll hooks. */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "real-backend.spec.ts",
  timeout: 120000,
  use: {
    headless: true,
  },
  // No webServer config — backend is started programmatically in beforeAll.
});
