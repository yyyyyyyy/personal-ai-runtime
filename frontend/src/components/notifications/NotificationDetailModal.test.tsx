import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithRouter } from "../../test-utils";
import NotificationDetailModal from "./NotificationDetailModal";
import type { Notification } from "../../api/client";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const sampleNotification: Notification = {
  id: "n1",
  type: "goal_stagnant",
  title: "目标提醒",
  content: "你的目标本周无进展",
  created_at: "2026-06-10T08:00:00Z",
};

describe("NotificationDetailModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders null when notification is null", () => {
    const { container } = renderWithRouter(
      <NotificationDetailModal notification={null} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows title, type label and content", () => {
    renderWithRouter(
      <NotificationDetailModal notification={sampleNotification} onClose={vi.fn()} />,
    );
    expect(screen.getByText("目标提醒")).toBeInTheDocument();
    expect(screen.getByText("目标")).toBeInTheDocument();
    expect(screen.getByText("你的目标本周无进展")).toBeInTheDocument();
  });

  it("calls onClose when close button clicked", () => {
    const onClose = vi.fn();
    renderWithRouter(
      <NotificationDetailModal notification={sampleNotification} onClose={onClose} />,
    );
    fireEvent.click(screen.getByLabelText("关闭"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when overlay clicked", () => {
    const onClose = vi.fn();
    renderWithRouter(
      <NotificationDetailModal notification={sampleNotification} onClose={onClose} />,
    );
    fireEvent.click(screen.getByText("目标提醒").closest(".fixed")!);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("does not close when content area clicked", () => {
    const onClose = vi.fn();
    renderWithRouter(
      <NotificationDetailModal notification={sampleNotification} onClose={onClose} />,
    );
    fireEvent.click(screen.getByText("你的目标本周无进展"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("navigates to related page", () => {
    const onClose = vi.fn();
    renderWithRouter(
      <NotificationDetailModal notification={sampleNotification} onClose={onClose} />,
    );
    fireEvent.click(screen.getByText("查看相关页面"));
    expect(onClose).toHaveBeenCalledOnce();
    expect(mockNavigate).toHaveBeenCalledWith("/goals");
  });

  it("navigates to dashboard for generic notification type", () => {
    const onClose = vi.fn();
    const generic: Notification = {
      ...sampleNotification,
      type: "custom_unknown_type",
    };
    renderWithRouter(<NotificationDetailModal notification={generic} onClose={onClose} />);
    fireEvent.click(screen.getByText("查看相关页面"));
    expect(onClose).toHaveBeenCalledOnce();
    expect(mockNavigate).toHaveBeenCalledWith("/dashboard");
  });
});
