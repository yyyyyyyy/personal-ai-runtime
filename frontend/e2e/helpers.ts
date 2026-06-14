import type { Page, Route } from "@playwright/test";

/** Match only real HTTP API paths (e.g. /api/goals), not Vite source like /src/api/goals.ts */
export function matchesApiPath(url: string, prefix: string): boolean {
  const pathname = new URL(url).pathname;
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export async function mockApiJson(
  page: Page,
  prefix: string,
  json: unknown,
  method?: string,
) {
  await page.route("**/*", async (route: Route) => {
    const req = route.request();
    if (!matchesApiPath(req.url(), prefix)) {
      return route.continue();
    }
    if (method && req.method() !== method) {
      return route.continue();
    }
    await route.fulfill({ json });
  });
}

export async function mockApiHandler(
  page: Page,
  prefix: string,
  handler: (route: Route) => Promise<void>,
) {
  await page.route("**/*", async (route: Route) => {
    if (!matchesApiPath(route.request().url(), prefix)) {
      return route.continue();
    }
    return handler(route);
  });
}
