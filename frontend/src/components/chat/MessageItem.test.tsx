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
      />,
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
      />,
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
      />,
    );
    expect(container.textContent).toBe("");
  });

  it("skips empty non-streaming assistant bubbles without tools", () => {
    const { container } = render(
      <MessageItem
        message={{
          id: "m4",
          role: "assistant",
          content: "   ",
        }}
      />,
    );
    expect(container.textContent).toBe("");
  });

  it("still renders empty assistant while streaming", () => {
    render(
      <MessageItem
        message={{
          id: "m5",
          role: "assistant",
          content: "",
          isStreaming: true,
        }}
      />,
    );
    expect(screen.getByText("🧠")).toBeInTheDocument();
  });

  it("shows thinking placeholder before first token", () => {
    render(
      <MessageItem
        message={{
          id: "m6",
          role: "assistant",
          content: "",
          isStreaming: true,
        }}
      />,
    );
    expect(screen.getByText("思考中…")).toBeInTheDocument();
  });

  it("does not show thinking placeholder once content streams in", () => {
    render(
      <MessageItem
        message={{
          id: "m7",
          role: "assistant",
          content: "你好",
          isStreaming: true,
        }}
      />,
    );
    expect(screen.queryByText("思考中…")).not.toBeInTheDocument();
    expect(screen.getByText("你好")).toBeInTheDocument();
  });

  it("does not show thinking placeholder when tools are running without text", () => {
    render(
      <MessageItem
        message={{
          id: "m8",
          role: "assistant",
          content: "",
          isStreaming: true,
          toolCalls: [{ index: 0, id: "tc1", function_name: "web_search", arguments: "{}" }],
        }}
      />,
    );
    expect(screen.queryByText("思考中…")).not.toBeInTheDocument();
  });
});
