import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithRouter, MockApiError } from "../test-utils";
import ApprovalsPage from "./Approvals";
import type { EnrichedApproval } from "../api/client";

const { addError } = vi.hoisted(() => ({
  addError: vi.fn(),
}));

vi.mock("../api/client", () => ({
  listEnrichedPendingApprovals: vi.fn(),
  approveApproval: vi.fn(),
  rejectApproval: vi.fn(),
  ApiError: MockApiError,
}));

vi.mock("../stores/errorStore", () => ({
  useErrorStore: (selector: (s: { addError: ReturnType<typeof vi.fn> }) => unknown) =>
    selector({ addError }),
}));

import { listEnrichedPendingApprovals, approveApproval, rejectApproval } from "../api/client";

const mockList = vi.mocked(listEnrichedPendingApprovals);
const mockApprove = vi.mocked(approveApproval);
const mockReject = vi.mocked(rejectApproval);

const sampleApproval: EnrichedApproval = {
  id: "ap-1",
  action: "write_file",
  status: "pending",
  params: JSON.stringify({ path: "/tmp/test.txt" }),
  created_at: new Date().toISOString(),
  flow_type: "对话",
  flow_label: "测试对话",
  correlation_id: "corr-1",
};

describe("ApprovalsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue([]);
  });

  it("shows loading state initially", () => {
    mockList.mockReturnValue(new Promise(() => {}));
    renderWithRouter(<ApprovalsPage />);
    expect(screen.getByText("加载中...")).toBeInTheDocument();
  });

  it("shows empty state when no approvals", async () => {
    renderWithRouter(<ApprovalsPage />);
    await waitFor(() => {
      expect(screen.getByText("暂无待审批项")).toBeInTheDocument();
    });
  });

  it("renders approval list", async () => {
    mockList.mockResolvedValue([sampleApproval]);
    renderWithRouter(<ApprovalsPage />);
    await waitFor(() => {
      expect(screen.getByText("写入文件")).toBeInTheDocument();
      expect(screen.getByText("1 条待处理")).toBeInTheDocument();
    });
  });

  it("removes item after approve", async () => {
    mockList.mockResolvedValueOnce([sampleApproval]).mockResolvedValue([]);
    mockApprove.mockResolvedValue({ id: "ap-1", status: "approved" });
    renderWithRouter(<ApprovalsPage />);
    await waitFor(() => expect(screen.getByText("批准")).toBeInTheDocument());
    fireEvent.click(screen.getByText("批准"));
    await waitFor(() => {
      expect(mockApprove).toHaveBeenCalledWith("ap-1");
      expect(screen.getByText("暂无待审批项")).toBeInTheDocument();
    });
  });

  it("removes item after reject", async () => {
    mockList.mockResolvedValueOnce([sampleApproval]).mockResolvedValue([]);
    mockReject.mockResolvedValue({ id: "ap-1", status: "rejected" });
    renderWithRouter(<ApprovalsPage />);
    await waitFor(() => expect(screen.getByText("拒绝")).toBeInTheDocument());
    fireEvent.click(screen.getByText("拒绝"));
    await waitFor(() => {
      expect(mockReject).toHaveBeenCalledWith("ap-1", "手动拒绝");
      expect(screen.getByText("暂无待审批项")).toBeInTheDocument();
    });
  });

  it("calls addError when load fails", async () => {
    mockList.mockRejectedValue(new MockApiError("加载失败", 500));
    renderWithRouter(<ApprovalsPage />);
    await waitFor(() => {
      expect(addError).toHaveBeenCalledWith("加载失败", "审批");
    });
  });
});
