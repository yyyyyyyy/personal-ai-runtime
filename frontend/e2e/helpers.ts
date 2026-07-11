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
    const sorted = [...this.routes.entries()].sort((a, b) => b[0].length - a[0].length);
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

export async function mockApiJson(page: Page, prefix: string, json: unknown, method?: string) {
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

export const E2E_CONV_ID = "e2e-conv-1";

/** Shared baseline API mocks used across e2e specs. */
export function buildCommonMocks(): MockApiRouter {
  const llmSettings = {
    config: {
      providers: [],
      default_provider: "deepseek",
      temperature: 0.7,
      max_tokens: 4096,
    },
  };
  const emailSettings = {
    config: { user: "", password: "", imap_host: "", smtp_host: "" },
  };

  return new MockApiRouter()
    .json("/api/system/health", {
      status: "ok",
      service: "personal-ai",
      auth_required: false,
    })
    .json("/api/system/info", { conversations: 1, goals: 3, memories: 25, messages: 42 })
    .json("/api/system/llm-providers", { providers: [], default: "deepseek-chat" })
    .json("/api/system/mcp-status", { enabled: false, servers: [], total_tools: 0 })
    .json("/api/settings/llm", llmSettings)
    .json("/api/settings/email", emailSettings)
    .json("/api/inbox", [])
    .json("/api/goals", [
      {
        id: "goal-1",
        title: "学习 Rust",
        description: "通过实践项目学习 Rust",
        status: "active",
        priority: "high",
        progress: 0.3,
        created_at: "2026-06-01T00:00:00Z",
        updated_at: "2026-06-15T00:00:00Z",
        last_activity_at: "2026-06-15T00:00:00Z",
      },
    ])
    .json("/api/work-items", [
      {
        id: "goal-1",
        title: "学习 Rust",
        description: "通过实践项目学习 Rust",
        work_type: "goal",
        parent_work_id: null,
        parent_goal_id: null,
        status: "active",
        priority: 0,
        dependencies_json: null,
        executable_plan: null,
        progress: 0.3,
        importance: 0.5,
        urgency: 0.5,
        deadline: null,
        created_at: "2026-06-01T00:00:00Z",
        updated_at: "2026-06-15T00:00:00Z",
        completed_at: null,
        last_activity_at: "2026-06-15T00:00:00Z",
      },
    ])
    .handler(`/api/chat/conversations/${E2E_CONV_ID}/messages`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ json: [] });
        return;
      }
      await route.continue();
    })
    .handler("/api/chat/conversations", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          json: [
            {
              id: E2E_CONV_ID,
              title: "测试对话",
              summary: null,
              created_at: "2026-06-10T00:00:00Z",
              updated_at: "2026-06-10T00:00:00Z",
            },
          ],
        });
        return;
      }
      await route.continue();
    })
    .json("/api/approvals", [])
    .json("/api/notifications", [])
    .json("/api/knowledge/documents", { documents: [], total: 0 })
    .json("/api/memory/memories/grouped", {
      memories: [
        {
          id: "mem-1",
          content: "用户喜欢喝咖啡",
          category: "偏好",
          created_at: "2026-06-10T00:00:00Z",
        },
      ],
    })
    .json("/api/memory/memories/search", [])
    .json("/api/dashboard", {
      generated_at: "2026-06-28T10:00:00Z",
      data_sovereignty: {
        total_events: 1250,
        total_memories: 121,
        memories_self_report: 45,
        memories_claim: 75,
        total_goals: 8,
        goals_active: 5,
        goals_completed: 3,
        total_conversations: 42,
        total_messages: 1250,
        data_location: "本地存储",
        last_belief_reflection: null,
        export_supported: true,
      },
      active_goals: { count: 5, top: [] },
      recent_events: { count: 0, total_in_window: 0, items: [] },
      recent_memories: { count: 0, items: [] },
      timer_status: { active_timers: 0, items: [] },
      governance_status: { active_policies: 10, active_grants: 5 },
    })
    .json("/api/timeline/events", {
      items: [],
      total: 0,
      page: 1,
      page_size: 30,
      has_more: false,
      icons: {},
    })
    .json("/api/telemetry/cost/summary", {
      total_prompt_tokens: 5000,
      total_completion_tokens: 3000,
      total_cost: 0.05,
      avg_latency_ms: 1200,
      total_calls: 42,
      failed_calls: 2,
    })
    .json("/api/telemetry/cost/by-model", [
      {
        provider: "deepseek",
        model: "deepseek-chat",
        total_calls: 30,
        prompt_tokens: 4000,
        completion_tokens: 2000,
        total_tokens: 6000,
        cost: 0.04,
        avg_latency_ms: 1100,
        failed_calls: 1,
      },
    ])
    .json("/api/telemetry/tool-summary", [
      { tool_name: "web_search", total_calls: 15, failed_calls: 1, avg_latency_ms: 800 },
    ])
    .json("/api/telemetry/memory/stats", {
      total_memories: 120,
      recent_7d: 8,
      categories: { habit: 30, work: 25 },
    })
    .json("/api/telemetry/health", {
      task_queue_length: 3,
      llm_failure_rate_24h: 0.01,
      tool_failure_rate_24h: 0.02,
    });
}

export async function installMocks(page: Page, extra?: (router: MockApiRouter) => void) {
  const router = buildCommonMocks();
  extra?.(router);
  await router.install(page);
}
