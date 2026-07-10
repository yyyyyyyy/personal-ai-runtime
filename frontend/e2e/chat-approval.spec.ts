import { test, expect, type Page } from "@playwright/test";
import { MockApiRouter, buildCommonMocks, installMocks, E2E_CONV_ID } from "./helpers";

const CONV_ID = E2E_CONV_ID;

test.describe("Navigation and pages", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("onboarding_done", "1"));
    await installMocks(page);
  });

  test("home page shows sidebar and navigation", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByText("Personal AI Runtime")).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("link", { name: "对话" })).toBeVisible();
  });

  test("navigation to goals page lists goals", async ({ page }) => {
    await page.goto("/goals");
    await expect(page).toHaveURL(/\/goals/);
    await expect(page.getByText("学习 Rust")).toBeVisible({ timeout: 5000 });
  });

  test("navigation to memories page shows memories", async ({ page }) => {
    await page.goto("/memories");
    await expect(page).toHaveURL(/\/memories/);
    await expect(page.getByText("用户喜欢喝咖啡")).toBeVisible({ timeout: 5000 });
  });

  test("dashboard page loads with overview", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByText("AI 概览")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("AI 记住了")).toBeVisible();
  });

  test("settings page shows export button", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("导出全部数据")).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole("heading", { name: "数据主权" })).toBeVisible();
  });

  test("approvals page shows empty state", async ({ page }) => {
    await page.goto("/approvals");
    await expect(page.getByText("审批管理")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/暂无待审批/)).toBeVisible();
  });
});

test.describe("Chat flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("onboarding_done", "1"));
    await installMocks(page);
  });

  test("chat input and send button present on conversation page", async ({ page }) => {
    await page.goto(`/chat/${CONV_ID}`);
    await expect(page.getByPlaceholder(/输入消息/)).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole("button", { name: "发送" })).toBeVisible();
  });
});

test.describe("Chat approval flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("onboarding_done", "1"));
  });

  test("shows confirmation dialog and resolves approval", async ({ page }) => {
    await installMocks(page, (router) => {
      router.handler(`/api/chat/conversations/${CONV_ID}/messages`, async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({ json: [] });
          return;
        }
        const sse =
          'data: {"type":"confirmation_required","tool_name":"write_file","tool_args":{"path":"/tmp/e2e.txt","content":"hello"},"approval_id":"ap-e2e-1","tool_call_id":"tc-e2e-1"}\n\n' +
          'data: {"type":"done"}\n\n';
        await route.fulfill({
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
          body: sse,
        });
      });
      router.handler("/api/chat/approvals/ap-e2e-1/resolve", async (route) => {
        await route.fulfill({ json: { status: "approved", result: '{"ok":true}' } });
      });
    });

    await page.goto(`/chat/${CONV_ID}`);
    await page.getByPlaceholder(/输入消息/).fill("请写入一个文件");
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText(/确认写入文件/)).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: "确认执行" }).click();
    await expect(page.getByText(/确认写入文件/)).not.toBeVisible({ timeout: 5000 });
  });

  test("user can deny pending tool approval", async ({ page }) => {
    await installMocks(page, (router) => {
      router.handler(`/api/chat/conversations/${CONV_ID}/messages`, async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({ json: [] });
          return;
        }
        const sse =
          'data: {"type":"confirmation_required","tool_name":"write_file","tool_args":{"path":"/tmp/e2e.txt","content":"hello"},"approval_id":"ap-e2e-2","tool_call_id":"tc-e2e-2"}\n\n' +
          'data: {"type":"done"}\n\n';
        await route.fulfill({
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
          body: sse,
        });
      });
      router.handler("/api/chat/approvals/ap-e2e-2/resolve", async (route) => {
        await route.fulfill({ json: { status: "denied" } });
      });
    });

    await page.goto(`/chat/${CONV_ID}`);
    await page.getByPlaceholder(/输入消息/).fill("请写入一个文件");
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText(/确认写入文件/)).toBeVisible({ timeout: 10000 });

    const dialog = page.locator(".bg-amber-900\\/30");
    await dialog.getByRole("button", { name: "取消" }).click();
    await expect(page.getByText(/确认写入文件/)).not.toBeVisible({ timeout: 5000 });
  });
});

test.describe("Error handling", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("onboarding_done", "1"));
  });

  test("dashboard shows error state on API failure", async ({ page }) => {
    const router = new MockApiRouter()
      .json("/api/system/health", { status: "ok", service: "personal-ai", auth_required: false })
      .json("/api/system/info", { conversations: 0, goals: 0, memories: 0, messages: 0 })
      .json("/api/goals", [])
      .json("/api/memory/memories/grouped", { memories: [] })
      .json("/api/memory/memories/search", [])
      .json("/api/notifications", [])
      .json("/api/inbox", [])
      .json("/api/settings/llm", {
        config: { providers: [], default_provider: "deepseek", temperature: 0.7, max_tokens: 4096 },
      })
      .json("/api/settings/email", {
        config: { user: "", password: "", imap_host: "", smtp_host: "" },
      })
      .json("/api/approvals", [])
      .json("/api/system/llm-providers", { providers: [], default: "deepseek-chat" })
      .json("/api/system/mcp-status", { enabled: false, servers: [], total_tools: 0 })
      .handler("/api/chat/conversations", async (route) => {
        await route.fulfill({ json: [] });
      })
      .handler("/api/telemetry/cost/summary", async (route) => {
        await route.fulfill({ status: 500, body: "Internal Server Error" });
      })
      .handler("/api/telemetry/cost/by-model", async (route) => {
        await route.fulfill({ status: 500 });
      })
      .handler("/api/telemetry/tool-summary", async (route) => {
        await route.fulfill({ status: 500 });
      })
      .handler("/api/telemetry/memory/stats", async (route) => {
        await route.fulfill({ status: 500 });
      })
      .handler("/api/telemetry/health", async (route) => {
        await route.fulfill({ status: 500 });
      });

    await router.install(page);
    await page.goto("/dashboard");
    await expect(page.getByRole("button", { name: "重试" })).toBeVisible({ timeout: 10000 });
  });
});

test.describe("New pages (v0.1.0)", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("onboarding_done", "1"));
  });

  test("timeline page loads and shows events", async ({ page }) => {
    const router = buildCommonMocks();
    router.json("/api/timeline/events", {
      items: [
        {
          id: "evt-1",
          seq: 1,
          type: "GoalCreated",
          description: "创建了目标「学习 Rust」",
          actor: "user",
          ts: "2026-06-28T08:00:00Z",
          payload_snippet: { title: "学习 Rust" },
        },
        {
          id: "evt-2",
          seq: 2,
          type: "MemoryDerived",
          description: "AI 记住了新信息: 用户喜欢跑步",
          actor: "system",
          ts: "2026-06-28T09:00:00Z",
          payload_snippet: { content: "用户喜欢跑步" },
        },
        {
          id: "evt-3",
          seq: 3,
          type: "BeliefFormed",
          description: "AI 生成了新认知: 用户是早起型人",
          actor: "system",
          ts: "2026-06-27T21:30:00Z",
          payload_snippet: { content: "用户是早起型人" },
        },
      ],
      total: 3,
      page: 1,
      page_size: 30,
      has_more: false,
      icons: { GoalCreated: "target", MemoryDerived: "brain", BeliefFormed: "lightbulb" },
    });
    await router.install(page);

    await page.goto("/timeline");
    await expect(page.getByText("人生时间线")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("学习 Rust")).toBeVisible();
    await expect(page.getByText("用户喜欢跑步")).toBeVisible();
    await expect(page.getByText("用户是早起型人")).toBeVisible();
  });

  test("knowledge page shows upload zone", async ({ page }) => {
    const router = buildCommonMocks();
    router.json("/api/knowledge/documents", { documents: [], total: 0 });
    await router.install(page);

    await page.goto("/knowledge");
    await expect(page.getByText("知识库")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("上传文档，让 AI 搜索你的知识")).toBeVisible();
    await expect(page.getByText("还没有上传任何文档")).toBeVisible();
  });

  test("knowledge page lists uploaded documents", async ({ page }) => {
    const router = buildCommonMocks();
    router.json("/api/knowledge/documents", {
      documents: [
        {
          id: "doc-1",
          filename: "架构设计.md",
          size: 2048,
          chunks: 3,
          uploaded_at: "2026-06-28T10:00:00Z",
        },
        {
          id: "doc-2",
          filename: "API 文档.pdf",
          size: 15000,
          chunks: 12,
          uploaded_at: "2026-06-27T15:00:00Z",
        },
      ],
      total: 2,
    });
    await router.install(page);

    await page.goto("/knowledge");
    await expect(page.getByText("架构设计.md")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("API 文档.pdf")).toBeVisible();
    await expect(page.getByText("已上传文档 (2)")).toBeVisible();
  });

  test("dashboard shows data sovereignty panel", async ({ page }) => {
    const router = buildCommonMocks();
    router.json("/api/dashboard", {
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
        data_location: "本地存储 (SQLite + ChromaDB)",
        last_belief_reflection: "2026-06-27T21:30:00Z",
        export_supported: true,
      },
      active_goals: { count: 5, top: [] },
      recent_events: { count: 0, total_in_window: 0, items: [] },
      recent_memories: { count: 0, items: [] },
      timer_status: { active_timers: 0, items: [] },
      governance_status: { active_policies: 10, active_grants: 5 },
    });
    await router.install(page);

    await page.goto("/dashboard");
    await expect(page.getByText("我的数据")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("1,250")).toBeVisible(); // total_events
    await expect(page.getByText("121")).toBeVisible(); // total_memories
    await expect(page.getByText("全部本地存储")).toBeVisible();
    await expect(page.getByText("导出我的数据")).toBeVisible();
  });
});
