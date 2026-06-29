import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import DashboardPage from "./Dashboard";

function renderDashboard() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>
  );
}

vi.mock("../hooks/useDashboard", () => ({
  useDashboard: vi.fn(),
}));

vi.mock("../hooks/useNotifications", () => ({
  useNotifications: vi.fn(),
}));

import { useDashboard } from "../hooks/useDashboard";
import { useNotifications } from "../hooks/useNotifications";

const mockUseDashboard = vi.mocked(useDashboard);
const mockUseNotifications = vi.mocked(useNotifications);

function mockDashboardData(overrides: Partial<ReturnType<typeof useDashboard>> = {}) {
  mockUseDashboard.mockReturnValue({
    cost: {
      total_prompt_tokens: 5000,
      total_completion_tokens: 3000,
      total_cost: 0.05,
      avg_latency_ms: 1200,
      total_calls: 42,
      failed_calls: 2,
    },
    costByModel: [
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
    ],
    tools: [
      { tool_name: "web_search", total_calls: 15, failed_calls: 1, avg_latency_ms: 800 },
      { tool_name: "read_file", total_calls: 10, failed_calls: 0, avg_latency_ms: 200 },
    ],
    memory: {
      total_memories: 120,
      recent_7d: 8,
      categories: { habit: 30, work: 25 },
    },
    health: {
      task_queue_length: 3,
      llm_failure_rate_24h: 0.01,
      tool_failure_rate_24h: 0.02,
    },
    notifications: [
      {
        id: "n1",
        type: "trigger",
        title: "目标提醒",
        content: "你的目标本周无进展",
        created_at: "2026-06-10T08:00:00Z",
      },
    ],
    dashboard: null,
    loading: false,
    error: "",
    refresh: vi.fn(),
    ...overrides,
  });

  mockUseNotifications.mockReturnValue({
    toasts: [],
    liveNotifications: [],
    dismissToast: vi.fn(),
  });
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDashboardData();
  });

  it("renders dashboard title", () => {
    renderDashboard();
    expect(screen.getAllByText("AI 概览")[0]).toBeInTheDocument();
  });

  it("shows loading state", () => {
    mockDashboardData({ loading: true });
    renderDashboard();
    expect(screen.getAllByText("加载中...")[0]).toBeInTheDocument();
  });

  it("shows error state with retry button", () => {
    const mockRefresh = vi.fn();
    mockDashboardData({ error: "后端连接失败", loading: false, refresh: mockRefresh });
    renderDashboard();
    expect(screen.getAllByText("后端连接失败")[0]).toBeInTheDocument();
    const retryButtons = screen.getAllByText("重试");
    fireEvent.click(retryButtons[0]);
    expect(mockRefresh).toHaveBeenCalledOnce();
  });

  it("renders memory overview section", () => {
    renderDashboard();
    expect(screen.getAllByText("AI 记住了")[0]).toBeInTheDocument();
    expect(screen.getAllByText("条记忆")[0]).toBeInTheDocument();
    expect(screen.getAllByText("habit: 30")[0]).toBeInTheDocument();
  });

  it("renders proactive reminders section", () => {
    renderDashboard();
    expect(screen.getAllByText("AI 给你的提醒")[0]).toBeInTheDocument();
    expect(screen.getAllByText("目标提醒")[0]).toBeInTheDocument();
  });

  it("shows empty reminder message when none present", () => {
    mockDashboardData({ notifications: [] });
    mockUseNotifications.mockReturnValue({
      toasts: [],
      liveNotifications: [],
      dismissToast: vi.fn(),
    });
    renderDashboard();
    expect(screen.getAllByText("暂无提醒")[0]).toBeInTheDocument();
  });

  it("hides system diagnostics by default", () => {
    renderDashboard();
    expect(screen.queryByText("LLM 成功率")).not.toBeInTheDocument();
  });

  it("shows system diagnostics when expanded", () => {
    renderDashboard();
    fireEvent.click(screen.getByText("系统诊断（开发者用）"));
    expect(screen.getAllByText("LLM 成功率")[0]).toBeInTheDocument();
    expect(screen.getAllByText("95.2%")[0]).toBeInTheDocument();
  });

  it("shows tool calls in diagnostics", () => {
    renderDashboard();
    fireEvent.click(screen.getByText("系统诊断（开发者用）"));
    expect(screen.getAllByText("工具调用 (7天)")[0]).toBeInTheDocument();
    expect(screen.getAllByText("搜索网页")[0]).toBeInTheDocument();
  });

  it("calls refresh on button click", () => {
    const mockRefresh = vi.fn();
    mockDashboardData({ refresh: mockRefresh });
    renderDashboard();
    const refreshButtons = screen.getAllByText("刷新");
    fireEvent.click(refreshButtons[0]);
    expect(mockRefresh).toHaveBeenCalledOnce();
  });
});
