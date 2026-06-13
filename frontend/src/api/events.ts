/** Events API — timeline event listing. */

import { API_BASE, request } from "./core";
import type { TimelineEvent } from "./types";

export async function listEvents(
  days = 30,
  limit = 50
): Promise<TimelineEvent[]> {
  return request<TimelineEvent[]>(
    `${API_BASE}/events/?days=${days}&limit=${limit}`
  );
}
