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
  it("renders tool name and formatted arguments", () => {
    render(
      <ConfirmationDialog
        toolCall={toolCall}
        onConfirm={vi.fn()}
        onDeny={vi.fn()}
      />
    );

    expect(screen.getByText(/确认操作: write_file/)).toBeInTheDocument();
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
});
