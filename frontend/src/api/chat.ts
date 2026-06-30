/** Chat API — conversations, messages and SSE streaming. */

import { API_BASE, request, getAuthToken } from "./core";
import type { Conversation, Message, StreamEvent } from "./types";

export async function createConversation(title?: string): Promise<Conversation> {
  const url = title
    ? `${API_BASE}/chat/conversations?title=${encodeURIComponent(title)}`
    : `${API_BASE}/chat/conversations`;
  return request<Conversation>(url, { method: "POST" });
}

export async function listConversations(): Promise<Conversation[]> {
  return request<Conversation[]>(`${API_BASE}/chat/conversations`);
}

export async function deleteConversation(id: string): Promise<void> {
  return request<void>(`${API_BASE}/chat/conversations/${id}`, { method: "DELETE" });
}

export async function updateConversation(
  id: string,
  title: string
): Promise<{ status: string }> {
  const url = `${API_BASE}/chat/conversations/${id}?title=${encodeURIComponent(title)}`;
  return request<{ status: string }>(url, { method: "PATCH" });
}

export async function getMessages(convId: string): Promise<Message[]> {
  return request<Message[]>(`${API_BASE}/chat/conversations/${convId}/messages`);
}

export async function sendMessage(
  convId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
  onError: (error: string) => void,
  onDone: () => void
): Promise<void> {
  const url = `${API_BASE}/chat/conversations/${convId}/messages`;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ content }),
  });

  if (res.status === 401) {
    onError("认证失败，请检查 AUTH_TOKEN 与 VITE_AUTH_TOKEN 是否一致");
    return;
  }

  if (!res.ok) {
    onError(`请求失败 (HTTP ${res.status})`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    onError("响应体为空");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let lastByteTime = Date.now();
  const SSE_IDLE_TIMEOUT_MS = 30_000;

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      onDone();
      break;
    }

    lastByteTime = Date.now();
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
        if (event.type !== "ping") {
          onEvent(event);
        }
        if (event.type === "done" || event.type === "error") {
          onDone();
          return;
        }
      } catch {
        // Skip parse errors
      }
    }

    // Abort if no data received for too long (silent server hang)
    if (Date.now() - lastByteTime > SSE_IDLE_TIMEOUT_MS) {
      reader.cancel().catch(() => {});
      onError("连接超时，服务端无响应。请重试。");
      return;
    }
  }
}
