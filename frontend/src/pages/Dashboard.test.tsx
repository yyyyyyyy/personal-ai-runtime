import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import DashboardPage from "./Dashboard";

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
    tools: [
      { tool_name: "web_search", total_calls: 15, failed_calls: 1, avg_latency_ms: 800 },
      { tool_name: "read_file", total_calls: 10, failed_calls: 0, avg_latency_ms: 200 },
    ],
    memory: {
      total_memories: 120,
      recent_7d: 8,
      categories: { habit: 30, work: 25, personal: 20 },
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
        title: "周报建议",
        content: "你的目标'学习Rust'本周无进展",
        created_at: "2026-06-10T08:00:00Z",
      },
    ],
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
    render(<DashboardPage />);
    expect(screen.getAllByText("系统运行概览")[0]).toBeInTheDocument();
  });

  it("shows loading state", () => {
    mockDashboardData({ loading: true });
    render(<DashboardPage />);
    expect(screen.getAllByText("加载中...")[0]).toBeInTheDocument();
  });

  it("shows error state with retry button", () => {
    const mockRefresh = vi.fn();
    mockDashboardData({ error: "后端连接失败", loading: false, refresh: mockRefresh });
    render(<DashboardPage />);
    expect(screen.getAllByText("后端连接失败")[0]).toBeInTheDocument();
    const retryButtons = screen.getAllByText("重试");
    fireEvent.click(retryButtons[0]);
    expect(mockRefresh).toHaveBeenCalledOnce();
  });

  it("renders LLM success rate stat card", () => {
    render(<DashboardPage />);
    expect(screen.getAllByText("LLM 成功率 (24h)")[0]).toBeInTheDocument();
    expect(screen.getAllByText("95.2%")[0]).toBeInTheDocument();
  });

  it("renders task queue length", () => {
    render(<DashboardPage />);
    expect(screen.getAllByText("任务队列")[0]).toBeInTheDocument();
  });

  it("renders total memories count", () => {
    render(<DashboardPage />);
    expect(screen.getAllByText("总记忆数")[0]).toBeInTheDocument();
  });

  it("renders token usage section", () => {
    render(<DashboardPage />);
    expect(screen.getAllByText("Token 用量 (7天)")[0]).toBeInTheDocument();
    expect(screen.getByText(/8,000\s+tokens/)).toBeInTheDocument();
  });

  it("renders cost section", () => {
    render(<DashboardPage />);
    expect(screen.getAllByText("成本与延迟 (7天)")[0]).toBeInTheDocument();
    expect(screen.getAllByText("$0.0500")[0]).toBeInTheDocument();
  });

  it("renders tool summary section", () => {
    render(<DashboardPage />);
    expect(screen.getAllByText("工具调用详情 (7天)")[0]).toBeInTheDocument();
    expect(screen.getAllByText("web_search")[0]).toBeInTheDocument();
    expect(screen.getAllByText("read_file")[0]).toBeInTheDocument();
  });

  it("renders memory system section with categories", () => {
    render(<DashboardPage />);
    expect(screen.getAllByText("记忆系统")[0]).toBeInTheDocument();
    expect(screen.getAllByText("habit: 30")[0]).toBeInTheDocument();
    expect(screen.getAllByText("work: 25")[0]).toBeInTheDocument();
    expect(screen.getAllByText("personal: 20")[0]).toBeInTheDocument();
  });

  it("renders notifications section", () => {
    render(<DashboardPage />);
    expect(screen.getAllByText("主动建议 & 通知")[0]).toBeInTheDocument();
    expect(screen.getAllByText("周报建议")[0]).toBeInTheDocument();
  });

  it("shows empty notification message when none present", () => {
    mockDashboardData({ notifications: [] });
    mockUseNotifications.mockReturnValue({
      toasts: [],
      liveNotifications: [],
      dismissToast: vi.fn(),
    });
    render(<DashboardPage />);
    expect(
      screen.getAllByText("暂无主动建议（触发器每 30 分钟评估一次）")[0],
    ).toBeInTheDocument();
  });

  it("renders empty tool message when no tools", () => {
    mockDashboardData({ tools: [] });
    render(<DashboardPage />);
    expect(screen.getAllByText("暂无工具调用数据")[0]).toBeInTheDocument();
  });

  it("calls refresh on button click", () => {
    const mockRefresh = vi.fn();
    mockDashboardData({ refresh: mockRefresh });
    render(<DashboardPage />);
    const refreshButtons = screen.getAllByText("刷新");
    fireEvent.click(refreshButtons[0]);
    expect(mockRefresh).toHaveBeenCalledOnce();
  });
});
