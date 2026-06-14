import { test, expect, type Page } from "@playwright/test";
import { MockApiRouter } from "./helpers";

const CONV_ID = "e2e-conv-1";

function buildCommonMocks(): MockApiRouter {
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
      version: "1.0.0",
      auth_required: false,
    })
    .json("/api/system/info", {
      conversations: 0,
      goals: 0,
      memories: 0,
      messages: 0,
    })
    .json("/api/system/llm-providers", {
      providers: [],
      default: "deepseek-chat",
    })
    .json("/api/system/mcp-status", {
      enabled: false,
      servers: [],
      total_tools: 0,
    })
    .json("/api/settings/llm", llmSettings)
    .json("/api/settings/email", emailSettings)
    .json("/api/reviews", [])
    .json("/api/inbox", [])
    .handler(`/api/chat/conversations/${CONV_ID}/messages`, async (route) => {
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
              id: CONV_ID,
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
    .json("/api/goals", [])
    .json("/api/approvals", [])
    .json("/api/chat/approvals", {
      status: "denied",
      assistant_message: "操作已取消",
    })
    .json("/api/notifications", [])
    .json("/api/memory/memories/grouped", { memories: [] })
    .json("/api/memory/memories/search", []);
}

async function installMocks(page: Page, extra?: (router: MockApiRouter) => void) {
  const router = buildCommonMocks();
  extra?.(router);
  await router.install(page);
}

test.describe("Chat flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("onboarding_done", "1");
    });
    await installMocks(page);
  });

  test("home page shows greeting and new chat", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByText(/欢迎回来/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: "开始新对话" })).toBeVisible();
  });

  test("navigation to goals page", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "目标" }).click();
    await expect(page).toHaveURL(/\/goals/);
    await expect(page.getByText("目标").first()).toBeVisible();
  });

  test("settings page shows export button", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("导出全部数据")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "数据主权" })
    ).toBeVisible();
  });

  test("chat input and send button present on new conversation", async ({
    page,
  }) => {
    await page.goto(`/chat/${CONV_ID}`);
    await expect(page.getByPlaceholder(/输入消息/)).toBeVisible();
    await expect(page.getByRole("button", { name: "发送" })).toBeVisible();
  });
});

test.describe("Chat approval flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("onboarding_done", "1");
    });
  });

  test("shows confirmation dialog and resolves approval", async ({ page }) => {
    await installMocks(page, (router) => {
      router
        .handler(`/api/chat/conversations/${CONV_ID}/messages`, async (route) => {
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
        })
        .handler("/api/chat/approvals/ap-e2e-1/resolve", async (route) => {
          await route.fulfill({
            json: { status: "approved", result: '{"ok":true}' },
          });
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
