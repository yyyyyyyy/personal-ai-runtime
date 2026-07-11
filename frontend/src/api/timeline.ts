/** Timeline API — event log feed. */

import { API_BASE, request } from "./core";

export interface TimelineEvent {
  id: string;
  seq: number;
  type: string;
  description: string;
  actor: string;
  ts: string;
  payload_snippet: Record<string, string>;
}

export interface TimelineResponse {
  items: TimelineEvent[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  icons: Record<string, string>;
}

export async function listTimelineEvents(
  page = 1,
  pageSize = 30,
): Promise<TimelineResponse> {
  return request<TimelineResponse>(
    `${API_BASE}/timeline/events?page=${page}&page_size=${pageSize}`,
  );
}
