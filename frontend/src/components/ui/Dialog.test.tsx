import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Dialog from "./Dialog";

describe("Dialog", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <Dialog open={false} title="删除" onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("exposes dialog a11y attributes when open", () => {
    render(
      <Dialog
        open
        title="删除对话"
        description="此操作不可撤销"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("删除对话");
    expect(dialog).toHaveAccessibleDescription("此操作不可撤销");
  });

  it("calls onCancel when Escape is pressed", () => {
    const onCancel = vi.fn();
    render(<Dialog open title="删除" onConfirm={vi.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("Escape uses the latest onCancel after rerender", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(
      <Dialog open title="删除" onConfirm={vi.fn()} onCancel={first} />,
    );
    rerender(<Dialog open title="删除" onConfirm={vi.fn()} onCancel={second} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(second).toHaveBeenCalledOnce();
    expect(first).not.toHaveBeenCalled();
  });

  it("calls onCancel when backdrop is clicked", () => {
    const onCancel = vi.fn();
    const { container } = render(
      <Dialog open title="删除" onConfirm={vi.fn()} onCancel={onCancel} />,
    );
    // Outer presentation layer is the backdrop
    fireEvent.click(container.firstChild as HTMLElement);
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("does not cancel when clicking inside the panel", () => {
    const onCancel = vi.fn();
    render(<Dialog open title="删除" onConfirm={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("dialog"));
    expect(onCancel).not.toHaveBeenCalled();
  });
});
