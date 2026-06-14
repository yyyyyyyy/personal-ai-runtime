/** Inbox API — email listing, digest, polling. */

import { API_BASE, request } from "./core";
import type { InboxEmail } from "./types";

export async function listInboxEmails(
  category?: string,
  status = "pending"
): Promise<InboxEmail[]> {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (status) params.set("status", status);
  const qs = params.toString();
  const url = qs ? `${API_BASE}/inbox/?${qs}` : `${API_BASE}/inbox/`;
  return request<InboxEmail[]>(url);
}

export async function updateInboxEmailStatus(
  emailId: string,
  status: "pending" | "read" | "handled"
): Promise<{ id: string; status: string }> {
  return request(`${API_BASE}/inbox/${encodeURIComponent(emailId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function getInboxDigest(): Promise<{ title?: string; content?: string; message?: string }> {
  return request(`${API_BASE}/inbox/digest`);
}

export async function triggerInboxPoll(): Promise<Record<string, unknown>> {
  return request(`${API_BASE}/inbox/poll`, { method: "POST" });
}
