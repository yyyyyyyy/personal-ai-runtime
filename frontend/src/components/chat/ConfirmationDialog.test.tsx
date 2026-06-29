import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import ConfirmationDialog from "./ConfirmationDialog";

afterEach(() => {
  cleanup();
});

const toolCall = {
  index: 0,
  id: "tc-1",
  function_name: "write_file",
  arguments: JSON.stringify({ path: "/tmp/test.txt", content: "hello" }),
};

describe("ConfirmationDialog", () => {
  it("renders human-readable label and expandable arguments", () => {
    render(
      <ConfirmationDialog
        toolCall={toolCall}
        onConfirm={vi.fn()}
        onDeny={vi.fn()}
      />
    );

    // Human-readable label
    expect(screen.getByText(/确认写入文件/)).toBeInTheDocument();
    // Argument details are expandable — expand them
    const summary = screen.getByText("查看详细参数");
    fireEvent.click(summary);
    expect(screen.getByText(/"path"/)).toBeInTheDocument();
  });

  it("calls onConfirm when user approves", () => {
    const onConfirm = vi.fn();
    const onDeny = vi.fn();

    const { container } = render(
      <ConfirmationDialog
        toolCall={toolCall}
        onConfirm={onConfirm}
        onDeny={onDeny}
      />
    );

    const confirmBtn = within(container).getByRole("button", { name: "确认执行" });
    fireEvent.click(confirmBtn);

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onDeny).not.toHaveBeenCalled();
  });

  it("calls onDeny when user cancels", () => {
    const onConfirm = vi.fn();
    const onDeny = vi.fn();

    const { container } = render(
      <ConfirmationDialog
        toolCall={toolCall}
        onConfirm={onConfirm}
        onDeny={onDeny}
      />
    );

    const denyBtn = within(container).getByRole("button", { name: "取消" });
    fireEvent.click(denyBtn);

    expect(onDeny).toHaveBeenCalledOnce();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("shows patch preview for apply_patch", () => {
    render(
      <ConfirmationDialog
        toolCall={{
          index: 0,
          id: "tc-2",
          function_name: "apply_patch",
          arguments: JSON.stringify({
            path: "/tmp/app.py",
            old_string: "return 'hi'",
            new_string: "return 'hello'",
          }),
        }}
        onConfirm={vi.fn()}
        onDeny={vi.fn()}
      />
    );

    expect(screen.getByText("变更预览")).toBeInTheDocument();
    expect(screen.getByText(/− return 'hi'/)).toBeInTheDocument();
    expect(screen.getByText(/\+ return 'hello'/)).toBeInTheDocument();
  });

  it("shows write preview for write_file", () => {
    render(
      <ConfirmationDialog
        toolCall={{
          index: 0,
          id: "tc-3",
          function_name: "write_file",
          arguments: JSON.stringify({
            path: "/tmp/app.py",
            content: "print('hello world')",
          }),
        }}
        onConfirm={vi.fn()}
        onDeny={vi.fn()}
      />
    );

    expect(screen.getByText("写入内容预览")).toBeInTheDocument();
    expect(screen.getAllByText(/print\('hello world'\)/).length).toBeGreaterThan(0);
  });

  it("shows expandable full content for long patches", () => {
    const longText = "x".repeat(500);
    render(
      <ConfirmationDialog
        toolCall={{
          index: 0,
          id: "tc-4",
          function_name: "apply_patch",
          arguments: JSON.stringify({
            path: "/tmp/app.py",
            old_string: longText,
            new_string: "short",
          }),
        }}
        onConfirm={vi.fn()}
        onDeny={vi.fn()}
      />
    );

    expect(screen.getByText("查看完整内容")).toBeInTheDocument();
  });
});
