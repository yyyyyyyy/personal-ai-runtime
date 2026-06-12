import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import MemoriesPage from "./Memories";

vi.mock("../api/client", () => ({
  listMemoriesGrouped: vi.fn().mockResolvedValue({
    memories: [{ id: "m1", content: "喜欢早起跑步", confidence: 0.9, category: "habit" }],
  }),
}));

describe("MemoriesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders memories list", async () => {
    render(<MemoriesPage />);
    expect(await screen.findByText("记忆")).toBeInTheDocument();
    expect(screen.getByText("喜欢早起跑步")).toBeInTheDocument();
  });
});
