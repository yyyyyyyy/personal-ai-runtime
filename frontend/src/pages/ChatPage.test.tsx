import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { renderWithRouter } from "../test-utils";
import ChatPage from "./ChatPage";

vi.mock("../components/chat/ChatView", () => ({
  default: ({ conversationId }: { conversationId: string }) => (
    <div data-testid="chat-view">{conversationId}</div>
  ),
}));

vi.mock("../components/chat/ChatHome", () => ({
  default: () => <div data-testid="chat-home">home</div>,
}));

function renderChatPage(initialEntries: string[]) {
  return renderWithRouter(
    <Routes>
      <Route path="/" element={<ChatPage />} />
      <Route path="/chat/:conversationId" element={<ChatPage />} />
    </Routes>,
    { initialEntries },
  );
}

describe("ChatPage", () => {
  it("renders ChatHome when no conversationId", () => {
    renderChatPage(["/"]);
    expect(screen.getByTestId("chat-home")).toBeInTheDocument();
  });

  it("renders ChatView when conversationId is present", () => {
    renderChatPage(["/chat/conv-123"]);
    expect(screen.getByTestId("chat-view")).toHaveTextContent("conv-123");
  });
});
