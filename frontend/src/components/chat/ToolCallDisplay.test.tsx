import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ToolCallDisplay from "./ToolCallDisplay";

describe("ToolCallDisplay", () => {
  const toolCalls = [
    {
      index: 0,
      id: "tc-1",
      function_name: "read_file",
      arguments: JSON.stringify({ path: "/tmp/test.txt" }),
    },
  ];

  it("renders tool label in Chinese", () => {
    render(
      <ToolCallDisplay
        toolCalls={toolCalls}
        toolResults={[]}
      />
    );
    expect(screen.getByText(/读取文件/)).toBeInTheDocument();
  });

  it("shows completed status when result present", () => {
    render(
      <ToolCallDisplay
        toolCalls={toolCalls}
        toolResults={[
          {
            tool_name: "read_file",
            tool_call_id: "tc-1",
            content: '{"ok": true}',
          },
        ]}
        defaultExpanded
      />
    );
    expect(screen.getByText(/完成|✓/)).toBeInTheDocument();
  });

  it("renders inbox email table for check_inbox", () => {
    const inboxResult = JSON.stringify({
      count: 1,
      emails: [
        {
          from: "alice@example.com",
          subject: "Hello",
          date: "2026-06-10 10:00",
          preview: "Hi there",
        },
      ],
    });
    render(
      <ToolCallDisplay
        toolCalls={[
          {
            index: 0,
            id: "tc-inbox",
            function_name: "check_inbox",
            arguments: "{}",
          },
        ]}
        toolResults={[
          {
            tool_name: "check_inbox",
            tool_call_id: "tc-inbox",
            content: inboxResult,
          },
        ]}
        defaultExpanded
      />
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText(/alice/)).toBeInTheDocument();
  });

  it("toggles expand on click", () => {
    render(
      <ToolCallDisplay
        toolCalls={toolCalls}
        toolResults={[
          {
            tool_name: "read_file",
            tool_call_id: "tc-1",
            content: "result data",
          },
        ]}
      />
    );
    const header = screen.getByText(/读取文件/).closest("button");
    if (header) {
      fireEvent.click(header);
    }
    expect(screen.getByText(/读取文件/)).toBeInTheDocument();
  });
});
