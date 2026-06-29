import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PasswordInput } from "./Input";

describe("PasswordInput", () => {
  it("toggles input type between password and text", () => {
    const { container } = render(<PasswordInput value="sk-secret" onChange={vi.fn()} />);
    const input = container.querySelector("input") as HTMLInputElement;
    expect(input.type).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "显示密码" }));
    expect((container.querySelector("input") as HTMLInputElement).type).toBe("text");
    expect(screen.getByDisplayValue("sk-secret")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "隐藏密码" }));
    expect((container.querySelector("input") as HTMLInputElement).type).toBe("password");
  });

  it("shows hint placeholder when revealing saved masked secret", () => {
    render(
      <PasswordInput
        value="••••••••"
        isSavedSecret
        onChange={vi.fn()}
        placeholder="原始占位"
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "显示密码" }));
    expect(
      screen.getByPlaceholderText("密钥已保存，不可查看原文；输入新值以替换")
    ).toBeInTheDocument();
  });
});
