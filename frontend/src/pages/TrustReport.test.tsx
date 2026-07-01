import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TrustReportPage from "./TrustReport";

vi.mock("../api/trustReport", () => ({ getTrustReport: vi.fn() }));

import { getTrustReport, type TrustReportData } from "../api/trustReport";
const mockGetReport = vi.mocked(getTrustReport);

const BASE: TrustReportData = {
  system: { conversations: 1, messages: 10, goals: 0, memories: 0, event_log: 1 },
  approvals: [],
  cost: {
    total_calls: 1,
    total_prompt_tokens: 10,
    total_completion_tokens: 5,
    total_cost: 0,
    avg_latency_ms: 500,
    failed_calls: 0,
  },
  costByModel: [],
  tools: [],
  memory: { total_memories: 0, categories: {}, recent_7d: 0 },
  health: { task_queue_length: 0, llm_failure_rate_24h: 0, tool_failure_rate_24h: 0 },
  dashboard: null,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <TrustReportPage />
    </MemoryRouter>,
  );
}

describe("TrustReportPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows loading state", () => {
    mockGetReport.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText("正在生成信任报告…")).toBeInTheDocument();
  });

  it("shows error and retry", async () => {
    mockGetReport.mockRejectedValue(new Error("失败"));
    renderPage();
    await waitFor(() => expect(screen.getByText("失败")).toBeInTheDocument());
    fireEvent.click(screen.getByText("重试"));
    expect(mockGetReport).toHaveBeenCalledTimes(2);
  });

  it("shows data location section", async () => {
    mockGetReport.mockResolvedValue({
      ...BASE,
      system: { conversations: 5, messages: 42, goals: 0, memories: 12, event_log: 200 },
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("数据存储位置")).toBeInTheDocument();
      expect(screen.getByText("本地 (SQLite + Chroma)")).toBeInTheDocument();
      expect(screen.getByText("5")).toBeInTheDocument();
    });
  });

  it("shows AI activity section", async () => {
    mockGetReport.mockResolvedValue({
      ...BASE,
      system: { conversations: 1, messages: 10, goals: 0, memories: 0, event_log: 50 },
      cost: {
        total_calls: 15,
        total_prompt_tokens: 1000,
        total_completion_tokens: 500,
        total_cost: 0.01,
        avg_latency_ms: 600,
        failed_calls: 1,
      },
      costByModel: [
        {
          provider: "openai",
          model: "gpt-4",
          total_calls: 15,
          prompt_tokens: 1000,
          completion_tokens: 500,
          total_tokens: 1500,
          cost: 0.01,
          avg_latency_ms: 600,
          failed_calls: 1,
        },
      ],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("AI 做了什么")).toBeInTheDocument();
    });
    expect(screen.getAllByText("15 次").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("$0.0100").length).toBeGreaterThanOrEqual(2);
  });

  it("shows empty approvals", async () => {
    mockGetReport.mockResolvedValue(BASE);
    renderPage();
    await waitFor(() => expect(screen.getByText("没有等待审批的操作")).toBeInTheDocument());
  });

  it("shows pending approvals with flow context", async () => {
    mockGetReport.mockResolvedValue({
      ...BASE,
      approvals: [
        {
          id: "a1",
          action: "write_file",
          status: "pending",
          flow_type: "对话",
          flow_label: "讨论",
          correlation_id: "c1",
          proposed_by: "w",
        },
        {
          id: "a2",
          action: "send_email",
          status: "pending",
          flow_type: "任务",
          flow_label: "邮件",
          correlation_id: "c2",
          proposed_by: "w",
        },
      ],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("write_file")).toBeInTheDocument();
      expect(screen.getByText("send_email")).toBeInTheDocument();
    });
  });
});
