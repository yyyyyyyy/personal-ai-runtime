/** Notifications API — listing. */

import { API_BASE, request } from "./core";
import type { Notification } from "./types";

export async function listNotifications(limit = 20): Promise<Notification[]> {
  return request<Notification[]>(`${API_BASE}/notifications/?limit=${limit}`);
}
