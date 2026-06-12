import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import InboxPage from "./Inbox";

vi.mock("../api/client", () => ({
  listInboxEmails: vi.fn().mockResolvedValue([]),
  getInboxDigest: vi.fn().mockResolvedValue({ title: "今日摘要", content: "无新邮件" }),
  triggerInboxPoll: vi.fn().mockResolvedValue({}),
}));

describe("InboxPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders inbox title and poll button", async () => {
    render(<InboxPage />);
    expect(screen.getByText("收件箱")).toBeInTheDocument();
    expect(screen.getByText("立即轮询")).toBeInTheDocument();
    expect(await screen.findByText("今日摘要")).toBeInTheDocument();
  });
});
