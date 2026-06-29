/** Approval API — list pending and resolve. */

import { API_BASE, request } from "./core";
import type { Approval, EnrichedApproval } from "./types";

export async function listPendingApprovals(): Promise<Approval[]> {
  return request<Approval[]>(`${API_BASE}/approvals/?pending_only=true`);
}

/** List pending approvals with flow context (conversation/task origin). */
export async function listEnrichedPendingApprovals(): Promise<EnrichedApproval[]> {
  return request<EnrichedApproval[]>(`${API_BASE}/approvals/?pending_only=true&enriched=true`);
}

/** Simple approve/deny without resuming conversation. */
export async function approveApproval(approvalId: string): Promise<Approval> {
  return request<Approval>(`${API_BASE}/approvals/${approvalId}/approve`, {
    method: "POST",
  });
}

/** Simple reject without resuming conversation. */
export async function rejectApproval(approvalId: string, reason: string = ""): Promise<Approval> {
  return request<Approval>(
    `${API_BASE}/approvals/${approvalId}/reject`,
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    },
  );
}

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
