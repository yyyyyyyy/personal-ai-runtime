import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import MessageItem from "./MessageItem";

describe("MessageItem", () => {
  it("renders user message with Chinese label", () => {
    render(
      <MessageItem
        message={{
          id: "m1",
          role: "user",
          content: "你好",
        }}
      />
    );
    expect(screen.getByText("你好")).toBeInTheDocument();
    expect(screen.getByText("你")).toBeInTheDocument();
  });

  it("renders assistant markdown content", () => {
    render(
      <MessageItem
        message={{
          id: "m2",
          role: "assistant",
          content: "**加粗**文本",
        }}
      />
    );
    expect(screen.getByText("加粗")).toBeInTheDocument();
  });

  it("does not render system messages", () => {
    const { container } = render(
      <MessageItem
        message={{
          id: "m3",
          role: "system",
          content: "hidden",
        }}
      />
    );
    expect(container.textContent).toBe("");
  });
});
