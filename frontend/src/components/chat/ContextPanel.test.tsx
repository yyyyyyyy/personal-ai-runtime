import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ContextPanel from "./ContextPanel";
import {
  listGoals,
  searchMemories,
  listPendingApprovals,
} from "../../api/client";

vi.mock("../../api/client", () => ({
  listGoals: vi.fn(),
  searchMemories: vi.fn(),
  listPendingApprovals: vi.fn(),
}));

vi.mock("../../stores/errorStore", () => ({
  useErrorStore: (selector: (s: { addError: () => void }) => unknown) =>
    selector({ addError: vi.fn() }),
}));

const mockGoals = [
  {
    id: "g1",
    title: "学习 Rust",
    status: "active",
    progress: 30,
    importance: 3,
    urgency: 2,
    parent_id: null,
    created_at: "2026-06-01T00:00:00Z",
    last_activity_at: "2026-06-10T10:00:00Z",
    description: null,
    deadline: null,
    actions: [],
    events: [],
  },
  {
    id: "g2",
    title: "健身计划",
    status: "active",
    progress: 50,
    importance: 2,
    urgency: 2,
    parent_id: null,
    created_at: "2026-06-01T00:00:00Z",
    last_activity_at: "2026-06-09T10:00:00Z",
    description: null,
    deadline: null,
    actions: [],
    events: [],
  },
  {
    id: "g3",
    title: "旧目标",
    status: "active",
    progress: 10,
    importance: 1,
    urgency: 1,
    parent_id: null,
    created_at: "2026-06-01T00:00:00Z",
    last_activity_at: "2026-06-01T10:00:00Z",
    description: null,
    deadline: null,
    actions: [],
    events: [],
  },
  {
    id: "g4",
    title: "已完成",
    status: "completed",
    progress: 100,
    importance: 1,
    urgency: 1,
    parent_id: null,
    created_at: "2026-06-01T00:00:00Z",
    last_activity_at: "2026-06-11T10:00:00Z",
    description: null,
    deadline: null,
    actions: [],
    events: [],
  },
];

describe("ContextPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listGoals).mockResolvedValue(mockGoals);
    vi.mocked(searchMemories).mockResolvedValue([
      { id: "m1", content: "喜欢 Rust 所有权模型", category: "note", created_at: "" },
    ]);
    vi.mocked(listPendingApprovals).mockResolvedValue([
      { id: "a1", action: "write_file", status: "pending" },
    ]);
  });

  it("shows collapsed toggle when closed", () => {
    render(
      <MemoryRouter>
        <ContextPanel open={false} onToggle={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.getByText("上下文")).toBeInTheDocument();
  });

  it("loads and shows active goals sorted by last activity", async () => {
    render(
      <MemoryRouter>
        <ContextPanel open={true} onToggle={vi.fn()} />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("学习 Rust")).toBeInTheDocument();
    });
    expect(screen.getByText("健身计划")).toBeInTheDocument();
    expect(screen.getByText("旧目标")).toBeInTheDocument();
    expect(screen.queryByText("已完成")).not.toBeInTheDocument();
  });

  it("shows pending approvals and related memories", async () => {
    render(
      <MemoryRouter>
        <ContextPanel
          open={true}
          onToggle={vi.fn()}
          lastUserMessage="帮我解释 Rust 所有权"
        />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/待审批/)).toBeInTheDocument();
    });
    expect(screen.getByText("write_file")).toBeInTheDocument();
    expect(screen.getByText(/喜欢 Rust 所有权模型/)).toBeInTheDocument();
  });

  it("calls onToggle when collapse clicked", async () => {
    const onToggle = vi.fn();
    render(
      <MemoryRouter>
        <ContextPanel open={true} onToggle={onToggle} />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByText("收起"));
    expect(onToggle).toHaveBeenCalledOnce();
  });
});
