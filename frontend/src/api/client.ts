/** API client for Personal AI Runtime backend. */

const API_BASE = "/api";

let _authToken: string | null = null;

/** Set the Bearer token for API requests. Call this once after reading the
 *  token from localStorage or from the server health-check response. */
export function setAuthToken(token: string) {
  _authToken = token;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_authToken) {
    headers["Authorization"] = `Bearer ${_authToken}`;
  }
  return headers;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers as Record<string, string> | undefined),
    },
  });

  if (res.status === 401) {
    throw new ApiError("认证失败，请检查 AUTH_TOKEN 配置", 401);
  }

  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body.detail || body.message || "";
    } catch {
      // response is not JSON
    }
    const msg = detail || `请求失败 (HTTP ${res.status})`;
    throw new ApiError(msg, res.status);
  }

  return res.json();
}

// ── Types ───────────────────────────────────────────────────────────────────

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

export interface StreamEvent {
  type: "text_delta" | "tool_call_start" | "tool_result" | "confirmation_required" | "done" | "error";
  content?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_call_id?: string;
  approval_id?: string;
  tool_calls?: Array<{
    index: number;
    id: string;
    function_name: string;
    arguments: string;
  }>;
}

// ── Chat API ────────────────────────────────────────────────────────────────

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
  if (_authToken) {
    headers["Authorization"] = `Bearer ${_authToken}`;
  }

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ content }),
  });

  if (res.status === 401) {
    onError("认证失败，请检查 AUTH_TOKEN 配置");
    return;
  }

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

// ── Telemetry API ───────────────────────────────────────────────────────────

export interface CostSummary {
  total_calls: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cost: number;
  avg_latency_ms: number;
  failed_calls: number;
}

export interface ToolSummaryItem {
  tool_name: string;
  total_calls: number;
  failed_calls: number;
  avg_latency_ms: number;
}

export interface MemoryStats {
  total_memories: number;
  categories: Record<string, number>;
  recent_7d: number;
}

export interface HealthSnapshot {
  task_queue_length: number;
  llm_failure_rate_24h: number;
  tool_failure_rate_24h: number;
}

export async function getCostSummary(days: number = 7): Promise<CostSummary> {
  return request<CostSummary>(`${API_BASE}/telemetry/cost/summary?days=${days}`);
}

export async function getToolSummary(days: number = 7): Promise<ToolSummaryItem[]> {
  return request<ToolSummaryItem[]>(`${API_BASE}/telemetry/tool-summary?days=${days}`);
}

export async function getMemoryStats(): Promise<MemoryStats> {
  return request<MemoryStats>(`${API_BASE}/telemetry/memory/stats`);
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  content: string;
  created_at: string;
  read?: number;
}

export async function listNotifications(limit = 20): Promise<Notification[]> {
  return request<Notification[]>(`${API_BASE}/notifications/?limit=${limit}`);
}

export async function getHealth(): Promise<HealthSnapshot> {
  return request<HealthSnapshot>(`${API_BASE}/telemetry/health`);
}

// ── Reviews API ─────────────────────────────────────────────────────────────

export interface KeyInsightsParsed {
  surface?: string;
  insights?: string[];
  legacy?: boolean;
}

export interface Review {
  id: string;
  type: string;
  period_start: string;
  period_end: string;
  content: string;
  key_insights?: string;
  key_insights_parsed?: KeyInsightsParsed;
  created_at: string;
}

export async function listReviews(limit = 10): Promise<Review[]> {
  return request<Review[]>(`${API_BASE}/reviews/?limit=${limit}`);
}

// ── Memory API ──────────────────────────────────────────────────────────────

export interface MemoryRow {
  id: string;
  content: string;
  category?: string;
  origin?: string;
  claim_status?: string | null;
  confidence?: number;
  source?: string;
  created_at?: string;
}

export interface MemoriesGrouped {
  memories: MemoryRow[];
}

export interface SystemInfo {
  conversations: number;
  messages: number;
  goals: number;
  memories: number;
}

export async function fetchSystemInfo(): Promise<SystemInfo> {
  return request<SystemInfo>(`${API_BASE}/system/info`);
}

export async function listMemoriesGrouped(): Promise<MemoriesGrouped> {
  return request<MemoriesGrouped>(`${API_BASE}/memory/memories/grouped`);
}

// ── Inbox API ───────────────────────────────────────────────────────────────

export interface InboxEmail {
  id: string;
  sender: string;
  subject: string;
  preview: string;
  received_at: string;
  category: string;
  importance: number;
  reason: string;
  notified: number;
  digested: number;
  created_at: string;
}

export async function listInboxEmails(category?: string): Promise<InboxEmail[]> {
  const url = category
    ? `${API_BASE}/inbox/?category=${encodeURIComponent(category)}`
    : `${API_BASE}/inbox/`;
  return request<InboxEmail[]>(url);
}

export async function getInboxDigest(): Promise<{ title?: string; content?: string; message?: string }> {
  return request(`${API_BASE}/inbox/digest`);
}

export async function triggerInboxPoll(): Promise<Record<string, unknown>> {
  return request(`${API_BASE}/inbox/poll`, { method: "POST" });
}

// ── Approval API ────────────────────────────────────────────────────────────

export async function resolveApproval(
  approvalId: string,
  decision: "approve" | "deny",
  toolName: string,
  toolArgs: Record<string, unknown>,
  convId: string,
  toolCallId: string
): Promise<{ status: string; result?: string; assistant_message?: string }> {
  return request(`${API_BASE}/chat/approvals/${approvalId}/resolve`, {
    method: "POST",
    body: JSON.stringify({
      decision,
      tool_name: toolName,
      tool_args: toolArgs,
      conv_id: convId,
      tool_call_id: toolCallId,
    }),
  });
}
