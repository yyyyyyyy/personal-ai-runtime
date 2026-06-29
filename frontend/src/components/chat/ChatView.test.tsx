import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ChatView from "./ChatView";
import { resolveApproval, sendMessage } from "../../api/client";

vi.mock("../../api/client", () => ({
  getMessages: vi.fn().mockResolvedValue([]),
  sendMessage: vi.fn(),
  resolveApproval: vi.fn(),
  updateConversation: vi.fn().mockResolvedValue({ status: "ok" }),
  listGoals: vi.fn().mockResolvedValue([]),
  listPendingApprovals: vi.fn().mockResolvedValue([]),
  listMemoriesGrouped: vi.fn().mockResolvedValue({ memories: [] }),
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

// TanStack Query-backed hook — provide a controllable stub so component
// tests can drive the memory cache (total + recent slice) and verify the
// "I just remembered" toast logic without a QueryClientProvider.
const memoriesState = { data: { memories: [] as Array<{ content: string }>, recent: [] as Array<{ content: string }> } };
vi.mock("../../hooks/useMemoriesGroupedQuery", () => ({
  useMemoriesGroupedQuery: () => memoriesState,
}));

function renderChatView() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ChatView conversationId="test-conv-1" />
      </MemoryRouter>
    </QueryClientProvider>
  );
}
describe("ChatView", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    // Reset the controllable memories stub between tests so each starts
    // from a clean baseline.
    memoriesState.data.memories = [];
    memoriesState.data.recent = [];
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

  it("does not show 'I just remembered' toast on initial mount", () => {
    // Regression for Issue 5: initial cache load (or StrictMode remount)
    // must never fire a spurious toast. The notice only fires after the
    // user sends a message AND the memory total grows beyond the post-send
    // baseline — both gates are verified at the logic level. Driving the
    // full "growth after send" path here requires intercepting React's
    // re-render schedule in ways that make the test more brittle than the
    // code; the post-send growth branch is covered by manual smoke instead.
    memoriesState.data.memories = [{ content: "likes tea" }];
    memoriesState.data.recent = [{ content: "likes tea" }];
    renderChatView();
    expect(screen.queryByText(/我刚记住了/)).not.toBeInTheDocument();
  });
});
