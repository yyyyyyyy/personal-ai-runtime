/** Notifications API — listing and read state. */

import { API_BASE, request } from "./core";
import type { Notification } from "./types";

export async function listNotifications(
  limit = 20,
  unreadOnly = false,
): Promise<Notification[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (unreadOnly) params.set("unread_only", "true");
  return request<Notification[]>(`${API_BASE}/notifications/?${params}`);
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  await request(`${API_BASE}/notifications/${notificationId}/read`, {
    method: "PUT",
  });
}

export async function markAllNotificationsRead(): Promise<void> {
  await request(`${API_BASE}/notifications/read-all`, { method: "PUT" });
}
