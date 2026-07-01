import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Sidebar from "./Sidebar";

function renderSidebar(initialEntry = "/", overrides = {}) {
  const defaultProps = {
    conversations: [
      { id: "c1", title: "Rust学习讨论" },
      { id: "c2", title: "周末计划" },
    ],
    activeConversationId: "c1",
    onSelectConversation: vi.fn(),
    onNewChat: vi.fn(),
    onDeleteChat: vi.fn(),
    ...overrides,
  };
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Sidebar {...defaultProps} />
    </MemoryRouter>,
  );
}

describe("Sidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders app title", () => {
    renderSidebar();
    expect(screen.getByText("Personal AI Runtime")).toBeInTheDocument();
    expect(screen.getByText("你的第二大脑")).toBeInTheDocument();
  });

  it("shows chat as primary nav and settings on chat route", () => {
    renderSidebar();
    expect(screen.getAllByText("对话").length).toBeGreaterThan(0);
    expect(screen.getAllByText("设置")[0]).toBeInTheDocument();
  });

  it("shows conversation list on chat route", () => {
    renderSidebar();
    expect(screen.getByText("Rust学习讨论")).toBeInTheDocument();
    expect(screen.getByText("周末计划")).toBeInTheDocument();
  });

  it("hides data nav items on chat route", () => {
    renderSidebar();
    expect(screen.queryByText("目标")).not.toBeInTheDocument();
    expect(screen.queryByText("收件箱")).not.toBeInTheDocument();
  });

  it("shows data nav items on non-chat route", () => {
    renderSidebar("/goals");
    expect(screen.getAllByText("目标")[0]).toBeInTheDocument();
    expect(screen.getAllByText("收件箱")[0]).toBeInTheDocument();
    expect(screen.getAllByText("记忆")[0]).toBeInTheDocument();
  });

  it("calls onSelectConversation when conversation clicked", () => {
    const onSelectConversation = vi.fn();
    renderSidebar("/", { onSelectConversation });
    fireEvent.click(screen.getByText("周末计划"));
    expect(onSelectConversation).toHaveBeenCalledWith("c2");
  });

  it("calls onNewChat when + 新对话 clicked", () => {
    const onNewChat = vi.fn();
    renderSidebar("/", { onNewChat });
    fireEvent.click(screen.getByText("+ 新对话"));
    expect(onNewChat).toHaveBeenCalled();
  });

  it("calls onDeleteChat when delete button clicked", () => {
    const onDeleteChat = vi.fn();
    renderSidebar("/", { onDeleteChat });
    const deleteButtons = screen.getAllByLabelText("删除对话");
    fireEvent.click(deleteButtons[0]);
    expect(onDeleteChat).toHaveBeenCalledWith("c1");
  });
});
