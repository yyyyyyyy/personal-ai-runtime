import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import MemoriesPage from "./Memories";

vi.mock("../api/client", () => ({
  listMemoriesGrouped: vi.fn().mockResolvedValue({
    memories: [{ id: "m1", content: "喜欢早起跑步", confidence: 0.9, category: "habit" }],
  }),
  createMemory: vi.fn(),
  deleteMemory: vi.fn(),
  createConversation: vi.fn(),
  ApiError: class extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../stores/errorStore", () => ({
  useErrorStore: (selector: (s: { addError: () => void }) => unknown) =>
    selector({ addError: vi.fn() }),
}));

vi.mock("../stores/chatStore", () => ({
  useChatStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      addConversation: vi.fn(),
      setActiveConversation: vi.fn(),
      setPendingPrompt: vi.fn(),
    }),
}));

describe("MemoriesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders memories list", async () => {
    render(
      <MemoryRouter>
        <MemoriesPage />
      </MemoryRouter>
    );
    expect(await screen.findByText("AI 对你的理解")).toBeInTheDocument();
    expect(screen.getByText("喜欢早起跑步")).toBeInTheDocument();
  });
});
