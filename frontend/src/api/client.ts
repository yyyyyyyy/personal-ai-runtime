/** API client for Personal AI Runtime backend. */

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
  approval_id?: string;
  tool_calls?: Array<{
    index: number;
    id: string;
    function_name: string;
    arguments: string;
  }>;
}

// --- Telemetry API ---

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
  const res = await fetch(`${API_BASE}/telemetry/cost/summary?days=${days}`);
  if (!res.ok) throw new Error("Failed to fetch cost summary");
  return res.json();
}

export async function getToolSummary(days: number = 7): Promise<ToolSummaryItem[]> {
  const res = await fetch(`${API_BASE}/telemetry/tool-summary?days=${days}`);
  if (!res.ok) throw new Error("Failed to fetch tool summary");
  return res.json();
}

export async function getMemoryStats(): Promise<MemoryStats> {
  const res = await fetch(`${API_BASE}/telemetry/memory/stats`);
  if (!res.ok) throw new Error("Failed to fetch memory stats");
  return res.json();
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
  const res = await fetch(`${API_BASE}/notifications/?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to list notifications");
  return res.json();
}

export async function getHealth(): Promise<HealthSnapshot> {
  const res = await fetch(`${API_BASE}/telemetry/health`);
  if (!res.ok) throw new Error("Failed to fetch health");
  return res.json();
}

// --- Reviews API ---

export interface KeyInsightsParsed {
  projection?: boolean;
  projection_type?: string;
  interpretive_plurality?: boolean;
  not_ratified?: boolean;
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
  const res = await fetch(`${API_BASE}/reviews/?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to list reviews");
  return res.json();
}

// --- Memory / Meaning API ---

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
  self_reports: MemoryRow[];
  claims: MemoryRow[];
  projection_note: string;
}

export interface SystemInfo {
  conversations: number;
  messages: number;
  goals: number;
  memories: number;
  experimental_trajectory_enabled: boolean;
}

export async function fetchSystemInfo(): Promise<SystemInfo> {
  const res = await fetch(`${API_BASE}/system/info`);
  if (!res.ok) throw new Error("Failed to fetch system info");
  return res.json();
}

export async function listMemoriesGrouped(): Promise<MemoriesGrouped> {
  const res = await fetch(`${API_BASE}/memory/memories/grouped`);
  if (!res.ok) throw new Error("Failed to list memories");
  return res.json();
}

export async function ratifyClaim(memoryId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/memory/memories/${memoryId}/ratify`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to ratify");
}

export async function rejectClaim(memoryId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/memory/memories/${memoryId}/reject`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to reject");
}

export interface TrajectorySummary {
  id: string;
  domain?: string;
  description?: string;
  status?: string;
  claim_status?: string;
  competing_with?: string[];
  identity_narrative_opt_in?: boolean;
}

export interface TrajectoryDetail {
  trajectory_id: string;
  registry: TrajectorySummary;
  links: TrajectoryPendingLink[];
  competing_with: string[];
  events: { seq: number; type: string; payload?: Record<string, unknown> }[];
}

export interface TrajectoryPendingLink {
  link_id: string;
  trajectory_id: string;
  event_seq: number;
  claim_status?: string;
  rationale?: string;
  confidence?: number;
  trajectory?: TrajectorySummary;
}

export async function listTrajectories(): Promise<{ trajectories: TrajectorySummary[] }> {
  const res = await fetch(`${API_BASE}/trajectories`);
  if (!res.ok) throw new Error("Failed to list trajectories");
  return res.json();
}

export async function getTrajectory(trajectoryId: string): Promise<TrajectoryDetail> {
  const res = await fetch(`${API_BASE}/trajectories/${encodeURIComponent(trajectoryId)}`);
  if (!res.ok) throw new Error("Failed to get trajectory");
  return res.json();
}

export async function listPendingTrajectoryLinks(): Promise<{ pending: TrajectoryPendingLink[] }> {
  const res = await fetch(`${API_BASE}/trajectories/pending-links`);
  if (!res.ok) throw new Error("Failed to list pending links");
  return res.json();
}

export async function ratifyTrajectoryLink(linkId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/trajectories/links/${linkId}/ratify`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to ratify link");
}

export async function rejectTrajectoryLink(linkId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/trajectories/links/${linkId}/reject`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to reject link");
}

export async function optInTrajectoryIdentity(trajectoryId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/trajectories/${encodeURIComponent(trajectoryId)}/identity-opt-in`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error("Failed to opt in trajectory identity");
}

export async function optOutTrajectoryIdentity(trajectoryId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/trajectories/${encodeURIComponent(trajectoryId)}/identity-opt-out`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error("Failed to opt out trajectory identity");
}

// --- Approval API ---

// --- Inbox API ---

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
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to list inbox emails");
  return res.json();
}

export async function getInboxDigest(): Promise<{ title?: string; content?: string; message?: string }> {
  const res = await fetch(`${API_BASE}/inbox/digest`);
  if (!res.ok) throw new Error("Failed to get inbox digest");
  return res.json();
}

export async function triggerInboxPoll(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/inbox/poll`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to poll inbox");
  return res.json();
}

export async function resolveApproval(
  approvalId: string,
  decision: "approve" | "deny",
  toolName: string,
  toolArgs: Record<string, unknown>,
  convId: string,
  toolCallId: string
): Promise<{ status: string; result?: string; assistant_message?: string }> {
  const res = await fetch(`${API_BASE}/chat/approvals/${approvalId}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision,
      tool_name: toolName,
      tool_args: toolArgs,
      conv_id: convId,
      tool_call_id: toolCallId,
    }),
  });
  if (!res.ok) throw new Error("Failed to resolve approval");
  return res.json();
}
