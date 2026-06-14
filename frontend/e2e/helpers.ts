import type { Page, Route } from "@playwright/test";

/** Match only real HTTP API paths (e.g. /api/goals), not Vite source like /src/api/goals.ts */
export function matchesApiPath(url: string, prefix: string): boolean {
  const pathname = new URL(url).pathname;
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

type MockHandler = (route: Route) => Promise<void>;

/** Consolidated API mock router — single page.route handler avoids route conflicts. */
export class MockApiRouter {
  private readonly routes = new Map<string, MockHandler>();

  /** Register a JSON response for an exact API prefix (GET by default). */
  json(prefix: string, body: unknown, method?: string): this {
    this.routes.set(prefix, async (route: Route) => {
      const req = route.request();
      if (method && req.method() !== method) {
        await route.continue();
        return;
      }
      await route.fulfill({ json: body });
    });
    return this;
  }

  /** Register a custom handler for an API prefix. */
  handler(prefix: string, fn: MockHandler): this {
    this.routes.set(prefix, fn);
    return this;
  }

  async install(page: Page): Promise<void> {
    const sorted = [...this.routes.entries()].sort(
      (a, b) => b[0].length - a[0].length,
    );
    await page.route("**/*", async (route: Route) => {
      const url = route.request().url();
      for (const [prefix, handler] of sorted) {
        if (matchesApiPath(url, prefix)) {
          return handler(route);
        }
      }
      await route.continue();
    });
  }
}

export async function mockApiJson(
  page: Page,
  prefix: string,
  json: unknown,
  method?: string,
) {
  const router = new MockApiRouter();
  router.json(prefix, json, method);
  await router.install(page);
}

export async function mockApiHandler(
  page: Page,
  prefix: string,
  handler: (route: Route) => Promise<void>,
) {
  const router = new MockApiRouter();
  router.handler(prefix, handler);
  await router.install(page);
}
