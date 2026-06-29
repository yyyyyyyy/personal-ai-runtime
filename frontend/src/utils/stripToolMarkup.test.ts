import { describe, expect, it } from "vitest";
import { hasToolMarkup, stripToolMarkup } from "./stripToolMarkup";

const SAMPLE =
  '<｜tool_calls> <｜invoke name="shell_exec"> ' +
  '<｜parameter name="command" string="true">curl http://localhost:5173</｜parameter> ' +
  "</｜invoke> </｜tool_calls>";

describe("stripToolMarkup", () => {
  it("detects tool markup", () => {
    expect(hasToolMarkup(SAMPLE)).toBe(true);
    expect(hasToolMarkup("<｜tool_calls>")).toBe(true);
    expect(hasToolMarkup("hello")).toBe(false);
  });

  it("removes tool-call blocks", () => {
    expect(stripToolMarkup("前缀 " + SAMPLE)).toBe("前缀");
    expect(stripToolMarkup(SAMPLE)).toBe("");
  });

  it("preserves internal newlines when trim is disabled", () => {
    expect(stripToolMarkup("第一行\n第二行", { trim: false })).toBe("第一行\n第二行");
    expect(stripToolMarkup("第一行\n", { trim: false })).toBe("第一行\n");
  });
});
