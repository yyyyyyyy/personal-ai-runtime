/** API client for Personal AI OS backend. */

const API_BASE = "/api";

export interface Conversation {
  id: string;
  title: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  tool_calls: string | null;
  tool_call_id: string | null;
  created_at: string;
}

export async function createConversation(title?: string): Promise<Conversation> {
  const url = title
    ? `${API_BASE}/chat/conversations?title=${encodeURIComponent(title)}`
    : `${API_BASE}/chat/conversations`;
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) throw new Error("Failed to create conversation");
  return res.json();
}

export async function listConversations(): Promise<Conversation[]> {
  const res = await fetch(`${API_BASE}/chat/conversations`);
  if (!res.ok) throw new Error("Failed to list conversations");
  return res.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/conversations/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete conversation");
}

export async function getMessages(convId: string): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/chat/conversations/${convId}/messages`);
  if (!res.ok) throw new Error("Failed to get messages");
  return res.json();
}

export async function sendMessage(
  convId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
  onError: (error: string) => void,
  onDone: () => void
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/conversations/${convId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });

  if (!res.ok) {
    onError(`HTTP error: ${res.status}`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    onError("No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      onDone();
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith("data: ")) continue;

      const data = trimmed.slice(6);
      if (data === "[DONE]") {
        onDone();
        return;
      }

      try {
        const event: StreamEvent = JSON.parse(data);
        onEvent(event);
        if (event.type === "done" || event.type === "error") {
          onDone();
          return;
        }
      } catch {
        // Skip parse errors
      }
    }
  }
}

export interface StreamEvent {
  type: "text_delta" | "tool_call_start" | "tool_result" | "confirmation_required" | "done" | "error";
  content?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_call_id?: string;
  tool_calls?: Array<{
    index: number;
    id: string;
    function_name: string;
    arguments: string;
  }>;
}
