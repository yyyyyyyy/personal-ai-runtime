import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import GoalsPage from "./Goals";

vi.mock("../api/client", () => ({
  listGoals: vi.fn().mockResolvedValue([]),
  getGoal: vi.fn(),
  createGoal: vi.fn(),
  updateGoal: vi.fn(),
  deleteGoal: vi.fn(),
  createGoalAction: vi.fn(),
  updateGoalAction: vi.fn(),
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

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({}),
  };
});

describe("GoalsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the goals page with title", () => {
    render(<GoalsPage />);

    expect(screen.getByText("目标")).toBeInTheDocument();
    const newButtons = screen.getAllByText("+ 新建");
    expect(newButtons.length).toBeGreaterThan(0);
  });

  it("shows create input after clicking + 新建", () => {
    render(<GoalsPage />);

    fireEvent.click(screen.getAllByText("+ 新建")[0]);

    expect(screen.getByPlaceholderText(/目标名称/)).toBeInTheDocument();
  });
});
