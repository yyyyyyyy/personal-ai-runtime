/** Reviews API — morning brief and review listing. */

import { API_BASE, request } from "./core";
import type { Review } from "./types";

export async function listReviews(limit = 10): Promise<Review[]> {
  return request<Review[]>(`${API_BASE}/reviews/?limit=${limit}`);
}

export async function triggerMorningBrief(): Promise<{
  status: string;
  result: string | Record<string, unknown>;
}> {
  return request(`${API_BASE}/reviews/trigger/morning-brief`, { method: "POST" });
}
