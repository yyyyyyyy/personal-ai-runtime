/** Inbox API — email listing, digest, polling. */

import { API_BASE, request } from "./core";
import type { InboxEmail } from "./types";

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
