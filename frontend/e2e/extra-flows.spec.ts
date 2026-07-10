import { test, expect } from "@playwright/test";
import { installMocks } from "./helpers";

test.describe("Extra core flows", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("onboarding_done", "1"));
  });

  test("knowledge search returns results", async ({ page }) => {
    await installMocks(page, (router) => {
      router.handler("/api/knowledge/search", async (route) => {
        await route.fulfill({
          json: {
            results: [
              {
                id: "r1",
                content: "Rust 所有权是核心概念",
                metadata: { source_file: "rust.md" },
                distance: 0.15,
              },
            ],
          },
        });
      });
    });

    await page.goto("/knowledge");
    await expect(page.getByText("知识库")).toBeVisible({ timeout: 5000 });
    await page.getByPlaceholder("在知识库中搜索…").fill("Rust");
    await page.getByRole("button", { name: "搜索" }).click();
    await expect(page.getByText("Rust 所有权是核心概念")).toBeVisible({ timeout: 5000 });
  });

  test("approvals page approve removes pending item", async ({ page }) => {
    let approved = false;
    await installMocks(page, (router) => {
      router.handler("/api/approvals", async (route) => {
        const req = route.request();
        if (req.method() === "GET") {
          if (approved) {
            await route.fulfill({ json: [] });
            return;
          }
          await route.fulfill({
            json: [
              {
                id: "ap-e2e-1",
                action: "write_file",
                status: "pending",
                params: JSON.stringify({ path: "/tmp/e2e.txt" }),
                created_at: "2026-06-28T10:00:00Z",
                flow_type: "对话",
                flow_label: "E2E 对话",
                correlation_id: "corr-e2e",
              },
            ],
          });
          return;
        }
        if (req.method() === "POST" && req.url().includes("/approve")) {
          approved = true;
          await route.fulfill({ json: { id: "ap-e2e-1", status: "approved" } });
          return;
        }
        await route.continue();
      });
    });

    await page.goto("/approvals");
    await expect(page.getByText("写入文件")).toBeVisible({ timeout: 5000 });
    await page.getByRole("button", { name: "批准" }).click();
    await expect(page.getByText("暂无待审批项")).toBeVisible({ timeout: 5000 });
  });

  test("approvals page reject removes pending item", async ({ page }) => {
    let rejected = false;
    await installMocks(page, (router) => {
      router.handler("/api/approvals", async (route) => {
        const req = route.request();
        if (req.method() === "GET") {
          if (rejected) {
            await route.fulfill({ json: [] });
            return;
          }
          await route.fulfill({
            json: [
              {
                id: "ap-e2e-2",
                action: "shell_exec",
                status: "pending",
                params: JSON.stringify({ command: "echo hi" }),
                created_at: "2026-06-28T10:00:00Z",
                flow_type: "任务",
                flow_label: "E2E 任务",
                correlation_id: "corr-e2e-2",
              },
            ],
          });
          return;
        }
        if (req.method() === "POST" && req.url().includes("/reject")) {
          rejected = true;
          await route.fulfill({ json: { id: "ap-e2e-2", status: "rejected" } });
          return;
        }
        await route.continue();
      });
    });

    await page.goto("/approvals");
    await expect(page.getByText("执行命令")).toBeVisible({ timeout: 5000 });
    await page.getByRole("button", { name: "拒绝" }).click();
    await expect(page.getByText("暂无待审批项")).toBeVisible({ timeout: 5000 });
  });

  test("notification bell opens detail modal", async ({ page }) => {
    await installMocks(page, (router) => {
      router.json("/api/notifications", [
        {
          id: "n-e2e-1",
          type: "goal_stagnant",
          title: "目标停滞提醒",
          content: "你的目标「学习 Rust」本周无进展",
          created_at: "2026-06-28T08:00:00Z",
          read: 0,
        },
      ]);
      router.handler("/api/notifications/n-e2e-1/read", async (route) => {
        await route.fulfill({ json: { ok: true } });
      });
    });

    await page.goto("/");
    await page.getByRole("button", { name: "通知" }).click();
    await expect(page.getByText("目标停滞提醒")).toBeVisible({ timeout: 5000 });
    await page.getByText("目标停滞提醒").click();
    await expect(page.getByRole("heading", { name: "目标停滞提醒" })).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("查看相关页面")).toBeVisible();
  });
});
