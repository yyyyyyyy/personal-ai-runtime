import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithRouter } from "../test-utils";
import TimelinePage from "./Timeline";

vi.mock("../api/core", () => ({
  API_BASE: "/api",
  request: vi.fn(),
}));

import { request } from "../api/core";

const mockRequest = vi.mocked(request);

const makeEvent = (id: string, description: string, ts: string) => ({
  id,
  seq: 1,
  type: "GoalCreated",
  description,
  actor: "user",
  ts,
  payload_snippet: {},
});

describe("TimelinePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading initially", () => {
    mockRequest.mockReturnValue(new Promise(() => {}));
    renderWithRouter(<TimelinePage />);
    expect(document.querySelector(".animate-spin")).toBeTruthy();
  });

  it("renders events grouped by day", async () => {
    mockRequest.mockResolvedValue({
      items: [
        makeEvent("e1", "创建了目标「学习 Rust」", "2026-06-28T08:00:00Z"),
        makeEvent("e2", "AI 记住了新信息", "2026-06-28T09:00:00Z"),
      ],
      total: 2,
      page: 1,
      page_size: 30,
      has_more: false,
      icons: { GoalCreated: "target" },
    });
    renderWithRouter(<TimelinePage />);
    await waitFor(() => {
      expect(screen.getByText("人生时间线")).toBeInTheDocument();
      expect(screen.getByText("创建了目标「学习 Rust」")).toBeInTheDocument();
      expect(screen.getByText("2 个事件")).toBeInTheDocument();
    });
  });

  it("shows empty state", async () => {
    mockRequest.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 30,
      has_more: false,
      icons: {},
    });
    renderWithRouter(<TimelinePage />);
    await waitFor(() => {
      expect(screen.getByText("还没有任何事件")).toBeInTheDocument();
    });
  });

  it("loads more on button click", async () => {
    mockRequest
      .mockResolvedValueOnce({
        items: [makeEvent("e1", "事件一", "2026-06-28T08:00:00Z")],
        total: 2,
        page: 1,
        page_size: 30,
        has_more: true,
        icons: {},
      })
      .mockResolvedValueOnce({
        items: [makeEvent("e2", "事件二", "2026-06-27T08:00:00Z")],
        total: 2,
        page: 2,
        page_size: 30,
        has_more: false,
        icons: {},
      });
    renderWithRouter(<TimelinePage />);
    await waitFor(() => expect(screen.getByText("事件一")).toBeInTheDocument());
    fireEvent.click(screen.getByText("加载更多"));
    await waitFor(() => {
      expect(screen.getByText("事件二")).toBeInTheDocument();
      expect(mockRequest).toHaveBeenCalledTimes(2);
    });
  });

  it("shows error with retry", async () => {
    mockRequest.mockRejectedValue(new Error("加载失败"));
    renderWithRouter(<TimelinePage />);
    await waitFor(() => {
      expect(screen.getByText("加载失败")).toBeInTheDocument();
    });
    mockRequest.mockResolvedValue({
      items: [makeEvent("e1", "恢复成功", "2026-06-28T08:00:00Z")],
      total: 1,
      page: 1,
      page_size: 30,
      has_more: false,
      icons: {},
    });
    fireEvent.click(screen.getByText("重试"));
    await waitFor(() => {
      expect(screen.getByText("恢复成功")).toBeInTheDocument();
    });
  });
});
