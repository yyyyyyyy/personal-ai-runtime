import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor, act } from "@testing-library/react";
import { renderWithRouter, MockApiError } from "../../test-utils";
import QuickCaptureDialog from "./QuickCaptureDialog";

const { addError } = vi.hoisted(() => ({
  addError: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  createMemory: vi.fn(),
  ApiError: MockApiError,
}));

vi.mock("../../stores/errorStore", () => ({
  useErrorStore: (selector: (s: { addError: ReturnType<typeof vi.fn> }) => unknown) =>
    selector({ addError }),
}));

import { createMemory } from "../../api/client";

const mockCreateMemory = vi.mocked(createMemory);

function openDialog() {
  act(() => {
    window.dispatchEvent(new MessageEvent("message", { data: { type: "quick-capture" } }));
  });
}

describe("QuickCaptureDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing by default", () => {
    const { container } = renderWithRouter(<QuickCaptureDialog />);
    expect(container.firstChild).toBeNull();
  });

  it("opens on quick-capture postMessage", async () => {
    renderWithRouter(<QuickCaptureDialog />);
    openDialog();
    await waitFor(() => {
      expect(screen.getByText("快速捕获")).toBeInTheDocument();
    });
  });

  it("opens on Ctrl+Shift+M", async () => {
    renderWithRouter(<QuickCaptureDialog />);
    fireEvent.keyDown(window, { key: "m", ctrlKey: true, shiftKey: true });
    await waitFor(() => {
      expect(screen.getByText("快速捕获")).toBeInTheDocument();
    });
  });

  it("disables save when text is empty", async () => {
    renderWithRouter(<QuickCaptureDialog />);
    openDialog();
    await waitFor(() => expect(screen.getByText("保存")).toBeInTheDocument());
    expect(screen.getByText("保存")).toBeDisabled();
  });

  it("saves memory on button click", async () => {
    mockCreateMemory.mockResolvedValue({ id: "mem-1", status: "ok" });
    renderWithRouter(<QuickCaptureDialog />);
    openDialog();
    await waitFor(() =>
      expect(screen.getByPlaceholderText("想到什么，立刻记下来...")).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByPlaceholderText("想到什么，立刻记下来..."), {
      target: { value: "重要想法" },
    });
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() => {
      expect(mockCreateMemory).toHaveBeenCalledWith({
        content: "重要想法",
        category: "quick_note",
      });
    });
  });

  it("saves on Cmd+Enter", async () => {
    mockCreateMemory.mockResolvedValue({ id: "mem-1", status: "ok" });
    renderWithRouter(<QuickCaptureDialog />);
    openDialog();
    const textarea = await screen.findByPlaceholderText("想到什么，立刻记下来...");
    fireEvent.change(textarea, { target: { value: "快捷键保存" } });
    fireEvent.keyDown(textarea, { key: "Enter", metaKey: true });
    await waitFor(() => {
      expect(mockCreateMemory).toHaveBeenCalledWith({
        content: "快捷键保存",
        category: "quick_note",
      });
    });
  });

  it("closes on Escape", async () => {
    renderWithRouter(<QuickCaptureDialog />);
    openDialog();
    const textarea = await screen.findByPlaceholderText("想到什么，立刻记下来...");
    fireEvent.keyDown(textarea, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByText("快速捕获")).not.toBeInTheDocument();
    });
  });

  it("calls addError when save fails", async () => {
    mockCreateMemory.mockRejectedValue(new MockApiError("保存失败", 500));
    renderWithRouter(<QuickCaptureDialog />);
    openDialog();
    await waitFor(() =>
      expect(screen.getByPlaceholderText("想到什么，立刻记下来...")).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByPlaceholderText("想到什么，立刻记下来..."), {
      target: { value: "会失败" },
    });
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() => {
      expect(addError).toHaveBeenCalledWith("保存失败", "记忆");
    });
  });
});
