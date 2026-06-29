#!/usr/bin/env node
/**
 * Capture real UI screenshots from the running Personal AI Runtime frontend.
 * Requires: the frontend (http://localhost:5173) and backend to be running.
 * Usage: node capture-screenshots.mjs
 */
import { chromium } from "playwright";
import { fileURLToPath } from "url";
import path from "path";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const BASE = "http://localhost:5173";
const VIEWPORT = { width: 1440, height: 900 };

// Pages to screenshot: [route, output filename, description]
const PAGES = [
  { route: "/",            out: "chat.png",          desc: "对话首页" },
  { route: "/goals",       out: "goals.png",         desc: "目标管理" },
  { route: "/inbox",       out: "inbox.png",         desc: "智能收件箱" },
  { route: "/dashboard",   out: "dashboard.png",     desc: "仪表盘" },
  { route: "/memories",    out: "memories.png",      desc: "记忆管理" },
];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: VIEWPORT });
// Skip first-run onboarding overlay (same flag as e2e tests / OnboardingWizard)
await context.addInitScript(() => {
  localStorage.setItem("onboarding_done", "1");
});
const page = await context.newPage();

for (const { route, out, desc } of PAGES) {
  const url = `${BASE}${route}`;
  const dest = path.join(ROOT, out);
  console.log(`📸 [${desc}] ${url} → ${out}`);
  await page.goto(url, { waitUntil: "networkidle", timeout: 15000 });
  // Give React a moment to fully render
  await page.waitForTimeout(1500);
  await page.screenshot({ path: dest, type: "png", fullPage: false });
  console.log(`  ✓ Wrote ${dest}`);
}

await browser.close();
console.log("\n✅ All screenshots captured.");
