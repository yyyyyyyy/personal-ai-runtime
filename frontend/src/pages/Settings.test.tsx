import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import SettingsPage from "./Settings";

vi.mock("../api/client", () => ({
  getSystemHealth: vi.fn().mockResolvedValue({
    status: "ok",
    version: "0.9.0",
    auth_required: false,
  }),
  fetchSystemInfo: vi.fn().mockResolvedValue({
    conversations: 5,
    goals: 2,
    memories: 10,
    messages: 20,
  }),
  getLlmSettings: vi.fn().mockResolvedValue({
    config: {
      default_provider: "deepseek",
      temperature: 0.7,
      max_tokens: 4096,
      providers: [
        {
          id: "deepseek",
          name: "DeepSeek",
          type: "openai_compatible",
          base_url: "https://api.deepseek.com/v1",
          model: "deepseek-chat",
          api_key: "••••••••",
          has_api_key: true,
          enabled: true,
        },
      ],
    },
    default_model: "deepseek-chat",
    providers_status: [
      { name: "deepseek", model: "deepseek-chat", type: "openai_compatible", is_default: true, available: true },
    ],
    presets: {
      deepseek: { name: "DeepSeek", type: "openai_compatible", base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
    },
    provider_types: { openai_compatible: "OpenAI 兼容" },
  }),
  updateLlmSettings: vi.fn(),
  testLlmConnection: vi.fn(),
  getEmailSettings: vi.fn().mockResolvedValue({
    config: {
      provider: "gmail",
      user: "test@gmail.com",
      password: "••••••••",
      imap_host: "imap.gmail.com",
      smtp_host: "smtp.gmail.com",
      smtp_port: 465,
      configured: true,
    },
    provider: "gmail",
    help: "使用 Gmail 应用专用密码",
  }),
  updateEmailSettings: vi.fn(),
  testEmailConnection: vi.fn(),
  getMcpStatus: vi.fn().mockResolvedValue({
    enabled: true,
    servers: [{ name: "playwright", status: "connected", tool_count: 5 }],
    total_tools: 5,
  }),
  exportData: vi.fn().mockResolvedValue({ events: [] }),
  importData: vi.fn(),
  ApiError: class extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../stores/errorStore", () => ({
  useErrorStore: (selector: (s: { addError: () => void }) => unknown) =>
    selector({ addError: vi.fn() }),
}));

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders system status and export button", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("设置")).toBeInTheDocument();
    });
    expect(screen.getByText("导出全部数据")).toBeInTheDocument();
    expect(screen.getByText("0.9.0")).toBeInTheDocument();
  });

  it("shows MCP server status", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("playwright")).toBeInTheDocument();
    });
    expect(screen.getByText("已连接")).toBeInTheDocument();
  });

  it("shows editable LLM and Gmail config sections", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Gmail 邮箱配置")).toBeInTheDocument();
    });
    expect(screen.getByText("保存 LLM 配置")).toBeInTheDocument();
    expect(screen.getByText("保存邮箱配置")).toBeInTheDocument();
    expect(screen.getByText("测试连接")).toBeInTheDocument();
  });
});
