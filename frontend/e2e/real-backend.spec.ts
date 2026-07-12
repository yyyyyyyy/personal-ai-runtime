import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import * as path from "node:path";
import * as http from "node:http";
import * as url from "node:url";
import * as fs from "node:fs";
import * as net from "node:net";
import * as os from "node:os";

const __filename = url.fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const PYTHON = process.platform === "win32" ? "python" : "python3";

let backendProc: ChildProcess | null = null;
let fakeLlmProc: ChildProcess | null = null;
let testDataDir = "";
let writeTarget = "";
let backendPort = 0;
let fakeLlmPort = 0;

async function freePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (!addr || typeof addr === "string") {
        reject(new Error("Could not allocate port"));
        return;
      }
      const port = addr.port;
      server.close(() => resolve(port));
    });
    server.on("error", reject);
  });
}

function waitForHealth(healthUrl: string, maxRetries = 60): Promise<void> {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      attempts++;
      http.get(healthUrl, (res) => {
        res.resume();
        if (res.statusCode === 200) resolve();
        else if (attempts >= maxRetries) {
          reject(new Error(`Health check returned ${res.statusCode} after ${attempts} attempts`));
        } else setTimeout(check, 500);
      }).on("error", () => {
        if (attempts >= maxRetries) reject(new Error(`Health check failed after ${attempts} attempts`));
        else setTimeout(check, 500);
      });
    };
    check();
  });
}

async function killProc(proc: ChildProcess | null): Promise<void> {
  if (!proc || proc.killed || proc.exitCode !== null) return;
  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      try { proc.kill("SIGKILL"); } catch { /* ignore */ }
      resolve();
    }, 5000);
    proc.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
    try { proc.kill("SIGTERM"); } catch { resolve(); }
  });
}

function parseSseEvents(text: string): Array<Record<string, unknown>> {
  const events: Array<Record<string, unknown>> = [];
  for (const line of text.split("\n")) {
    if (!line.startsWith("data:")) continue;
    const payload = line.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    try {
      events.push(JSON.parse(payload));
    } catch {
      // ignore non-JSON heartbeats
    }
  }
  return events;
}

test.describe("Real backend E2E — SSE chat + approval flow", () => {
  test.beforeAll(async () => {
    testDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "personal-ai-runtime-e2e-"));
    fs.mkdirSync(path.join(testDataDir, "vectors"), { recursive: true });
    writeTarget = path.join(
      REPO_ROOT,
      "backend",
      `.e2e-write-${process.pid}-${Date.now()}.txt`,
    );
    fakeLlmPort = await freePort();
    backendPort = await freePort();

    fakeLlmProc = spawn(PYTHON, [
      path.join(REPO_ROOT, "backend", "scripts", "fake_llm_server.py"),
      String(fakeLlmPort),
    ], {
      stdio: ["ignore", "pipe", "inherit"],
      env: {
        PATH: process.env.PATH,
        HOME: process.env.HOME,
        E2E_WRITE_PATH: writeTarget,
      },
    });

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Fake LLM start timed out")), 15000);
      fakeLlmProc!.once("error", (err) => {
        clearTimeout(timer);
        reject(err);
      });
      fakeLlmProc!.stdout!.once("data", (data: Buffer) => {
        clearTimeout(timer);
        if (data.toString().includes("FakeLLM listening")) resolve();
        else reject(new Error(`Unexpected fake LLM output: ${data}`));
      });
    });

    // Minimal env — do not inherit provider keys that could fall through to real APIs.
    const env: NodeJS.ProcessEnv = {
      PATH: process.env.PATH,
      HOME: process.env.HOME,
      PYTHONPATH: path.join(REPO_ROOT, "backend"),
      LLM_API_KEY: "fake-key",
      LLM_BASE_URL: `http://127.0.0.1:${fakeLlmPort}/v1`,
      LLM_MODEL: "fake-e2e",
      HOST: "127.0.0.1",
      PORT: String(backendPort),
      AUTH_TOKEN: "e2e-secret",
      DATA_DIR: testDataDir,
      VECTOR_DIR: path.join(testDataDir, "vectors"),
      SQLITE_PATH: path.join(testDataDir, "e2e.db"),
      MCP_EXTERNAL_ENABLED: "false",
      SENSITIVE_OPS_LOCAL: "false",
      OPENAI_API_KEY: "",
      ANTHROPIC_API_KEY: "",
      OLLAMA_BASE_URL: "",
      OLLAMA_MODEL: "",
      FILESYSTEM_ALLOWED_DIRS: REPO_ROOT,
      MAX_TOOL_ITERATIONS: "2",
    };

    backendProc = spawn(PYTHON, [
      "-m", "uvicorn", "app.main:app",
      "--host", "127.0.0.1",
      "--port", String(backendPort),
    ], {
      cwd: path.join(REPO_ROOT, "backend"),
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    backendProc.stderr!.on("data", (d: Buffer) => process.stderr.write(`[backend] ${d}`));
    backendProc.once("error", (err) => {
      throw err;
    });
    await waitForHealth(`http://127.0.0.1:${backendPort}/api/system/health`);
  });

  test.afterAll(async () => {
    await killProc(backendProc);
    await killProc(fakeLlmProc);
    try {
      fs.rmSync(testDataDir, { recursive: true, force: true });
    } catch (error) {
      console.warn(`Could not remove E2E data directory ${testDataDir}:`, error);
    }
    try {
      fs.rmSync(writeTarget, { force: true });
    } catch (error) {
      console.warn(`Could not remove E2E write target ${writeTarget}:`, error);
    }
  });

  test("health check returns ok or degraded", async ({ request }) => {
    const r = await request.get(`http://127.0.0.1:${backendPort}/api/system/health`);
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(["ok", "degraded"]).toContain(body.status);
  });

  test("SSE chat streams text_delta chunks then done", async ({ request }) => {
    const create = await request.post(`http://127.0.0.1:${backendPort}/api/chat/conversations`, {
      headers: { Authorization: "Bearer e2e-secret", "Content-Type": "application/json" },
      data: { title: "SSE Test" },
    });
    expect(create.status()).toBe(200);
    const convId = (await create.json()).id;

    const resp = await fetch(
      `http://127.0.0.1:${backendPort}/api/chat/conversations/${convId}/messages`,
      {
        method: "POST",
        headers: { Authorization: "Bearer e2e-secret", "Content-Type": "application/json" },
        body: JSON.stringify({ content: "hello" }),
      },
    );
    expect(resp.status).toBe(200);
    expect(resp.headers.get("content-type") || "").toContain("text/event-stream");

    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let full = "";
    let chunksSeen = 0;
    let firstChunkAt = 0;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (!firstChunkAt) firstChunkAt = Date.now();
      chunksSeen += 1;
      full += decoder.decode(value, { stream: true });
    }
    const streamFinishedAt = Date.now();
    full += decoder.decode();

    expect(chunksSeen).toBeGreaterThan(1);
    expect(streamFinishedAt - firstChunkAt).toBeGreaterThan(300);
    const events = parseSseEvents(full);
    const deltas = events.filter((e) => e.type === "text_delta");
    expect(deltas.length).toBeGreaterThan(0);
    const joined = deltas.map((e) => String(e.content || "")).join("");
    expect(joined).toContain("Hello");
    expect(events.some((e) => e.type === "done")).toBe(true);
  });

  test("tool call yields confirmation_required and approval can be resolved", async ({ request }) => {
    const create = await request.post(`http://127.0.0.1:${backendPort}/api/chat/conversations`, {
      headers: { Authorization: "Bearer e2e-secret", "Content-Type": "application/json" },
      data: { title: "Approval Test" },
    });
    expect(create.status()).toBe(200);
    const convId = (await create.json()).id;

    const resp = await fetch(
      `http://127.0.0.1:${backendPort}/api/chat/conversations/${convId}/messages`,
      {
        method: "POST",
        headers: { Authorization: "Bearer e2e-secret", "Content-Type": "application/json" },
        body: JSON.stringify({ content: "Please run E2E_TOOL_APPROVAL now" }),
      },
    );
    expect(resp.status).toBe(200);
    expect(resp.headers.get("content-type") || "").toContain("text/event-stream");
    const text = await resp.text();
    const events = parseSseEvents(text);

    const confirmation = events.find((e) => e.type === "confirmation_required");
    expect(confirmation).toBeTruthy();
    expect(confirmation!.tool_name).toBe("write_file");
    const approvalId = String(confirmation!.approval_id || "");
    const toolCallId = String(confirmation!.tool_call_id || "");
    expect(approvalId.length).toBeGreaterThan(0);
    expect(toolCallId.length).toBeGreaterThan(0);

    const pending = await request.get(
      `http://127.0.0.1:${backendPort}/api/approvals/?pending_only=true`,
      { headers: { Authorization: "Bearer e2e-secret" } },
    );
    expect(pending.status()).toBe(200);
    const list = await pending.json();
    expect(list.some((a: { id: string }) => a.id === approvalId)).toBe(true);

    const resolve = await request.post(
      `http://127.0.0.1:${backendPort}/api/chat/approvals/${approvalId}/resolve`,
      {
        headers: { Authorization: "Bearer e2e-secret", "Content-Type": "application/json" },
        data: {
          decision: "approve",
          tool_name: "write_file",
          conv_id: convId,
          tool_call_id: toolCallId,
        },
      },
    );
    expect(resolve.status()).toBe(200);
    const body = await resolve.json();
    expect(body.status).toBe("success");
    expect(String(body.assistant_message || "").length).toBeGreaterThan(0);
    expect(String(body.result || "")).toContain('"success": true');
    expect(fs.existsSync(writeTarget), JSON.stringify(body)).toBe(true);
    expect(fs.readFileSync(writeTarget, "utf8")).toContain("hello from e2e");

    const pendingAfter = await request.get(
      `http://127.0.0.1:${backendPort}/api/approvals/?pending_only=true`,
      { headers: { Authorization: "Bearer e2e-secret" } },
    );
    expect(pendingAfter.status()).toBe(200);
    const pendingList = await pendingAfter.json();
    expect(pendingList.some((a: { id: string }) => a.id === approvalId)).toBe(false);

    const resolveAgain = await request.post(
      `http://127.0.0.1:${backendPort}/api/chat/approvals/${approvalId}/resolve`,
      {
        headers: { Authorization: "Bearer e2e-secret", "Content-Type": "application/json" },
        data: {
          decision: "approve",
          tool_name: "write_file",
          conv_id: convId,
          tool_call_id: toolCallId,
        },
      },
    );
    expect(resolveAgain.status()).toBe(409);

    const messages = await request.get(
      `http://127.0.0.1:${backendPort}/api/chat/conversations/${convId}/messages`,
      { headers: { Authorization: "Bearer e2e-secret" } },
    );
    expect(messages.status()).toBe(200);
    const history = await messages.json();
    expect(
      history.some(
        (message: { role?: string; tool_call_id?: string }) =>
          message.role === "tool" && message.tool_call_id === toolCallId,
      ),
    ).toBe(true);
  });
});
