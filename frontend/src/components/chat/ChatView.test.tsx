import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ChatView from "./ChatView";
import { resolveApproval, sendMessage } from "../../api/client";

vi.mock("../../api/client", () => ({
  getMessages: vi.fn().mockResolvedValue([]),
  sendMessage: vi.fn(),
  resolveApproval: vi.fn(),
  updateConversation: vi.fn().mockResolvedValue({ status: "ok" }),
  listGoals: vi.fn().mockResolvedValue([]),
  listPendingApprovals: vi.fn().mockResolvedValue([]),
  searchMemories: vi.fn().mockResolvedValue([]),
  ApiError: class extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../../stores/errorStore", () => ({
  useErrorStore: (selector: (s: { addError: () => void }) => unknown) =>
    selector({ addError: vi.fn() }),
}));

vi.mock("../../stores/chatStore", () => ({
  useChatStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      conversations: [],
      updateConversationTitle: vi.fn(),
      pendingPrompt: null,
      setPendingPrompt: vi.fn(),
    }),
}));

function renderChatView() {
  return render(
    <MemoryRouter>
      <ChatView conversationId="test-conv-1" />
    </MemoryRouter>
  );
}

describe("ChatView", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders input area and send button", () => {
    renderChatView();

    expect(screen.getByPlaceholderText(/输入消息/)).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: "发送" });
    expect(buttons.length).toBeGreaterThan(0);
  });

  it("disables send button when input is empty", () => {
    renderChatView();

    const buttons = screen.getAllByRole("button", { name: "发送" });
    for (const button of buttons) {
      expect(button).toBeDisabled();
    }
  });

  it("shows approval dialog when stream requests confirmation", async () => {
    vi.mocked(sendMessage).mockImplementation(
      async (_convId, _content, onEvent, _onError, onDone) => {
        onEvent({
          type: "confirmation_required",
          tool_name: "write_file",
          tool_args: { path: "/tmp/x", content: "data" },
          approval_id: "ap-test-1",
          tool_call_id: "tc-test-1",
        });
        onEvent({ type: "done" });
        onDone();
      }
    );

    renderChatView();

    const inputs = screen.getAllByPlaceholderText(/输入消息/);
    const input = inputs[inputs.length - 1];
    fireEvent.change(input, { target: { value: "create a file" } });

    const sendButtons = screen.getAllByRole("button", { name: "发送" });
    fireEvent.click(sendButtons[sendButtons.length - 1]);

    await waitFor(() => {
      expect(screen.getByText(/确认写入文件/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/抱歉，未能生成回复/)).not.toBeInTheDocument();
  });

  it("calls resolveApproval when user confirms pending tool", async () => {
    vi.mocked(sendMessage).mockImplementation(
      async (_convId, _content, onEvent, _onError, onDone) => {
        onEvent({
          type: "confirmation_required",
          tool_name: "write_file",
          tool_args: { path: "/tmp/x", content: "data" },
          approval_id: "ap-test-1",
          tool_call_id: "tc-test-1",
        });
        onEvent({ type: "done" });
        onDone();
      }
    );
    vi.mocked(resolveApproval).mockResolvedValue({
      status: "approved",
      result: '{"ok": true}',
      assistant_message: "File written.",
    });

    const { container } = renderChatView();

    const inputs = screen.getAllByPlaceholderText(/输入消息/);
    fireEvent.change(inputs[inputs.length - 1], {
      target: { value: "create a file" },
    });
    const sendButtons = screen.getAllByRole("button", { name: "发送" });
    fireEvent.click(sendButtons[sendButtons.length - 1]);

    await waitFor(() => {
      expect(screen.getByText(/确认写入文件/)).toBeInTheDocument();
    });

    const confirmBtn = within(container).getByRole("button", { name: "确认执行" });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(resolveApproval).toHaveBeenCalledWith(
        "ap-test-1",
        "approve",
        "write_file",
        { path: "/tmp/x", content: "data" },
        "test-conv-1",
        "tc-test-1"
      );
    });

    await waitFor(() => {
      expect(screen.getByText("File written.")).toBeInTheDocument();
    });
  });
});
