/**
 * Work Items API — unified endpoint for tasks, actions, goals.
 *
 * Sole HTTP client for Work. goals.ts is a thin Goal view-model
 * adapter over these helpers.
 */
import { API_BASE, request } from "./core";
import type { WorkItem, WorkItemType } from "./types";

export async function listWorkItems(workType?: WorkItemType, status?: string): Promise<WorkItem[]> {
  const params = new URLSearchParams();
  if (workType) params.set("work_type", workType);
  if (status) params.set("status", status);
  const qs = params.toString();
  const url = qs ? `${API_BASE}/work-items/?${qs}` : `${API_BASE}/work-items/`;
  return request<WorkItem[]>(url);
}

export async function getWorkItem(itemId: string, include?: string): Promise<WorkItem> {
  const qs = include ? `?include=${encodeURIComponent(include)}` : "";
  return request<WorkItem>(`${API_BASE}/work-items/${itemId}${qs}`);
}

export async function getChildren(itemId: string): Promise<WorkItem[]> {
  return request<WorkItem[]>(`${API_BASE}/work-items/${itemId}/children`);
}

export interface CreateWorkItemPayload {
  title: string;
  description?: string;
  work_type: WorkItemType;
  parent_work_id?: string;
  parent_goal_id?: string;
  priority?: number;
  dependencies?: string[];
  executable_plan?: string;
  status?: string;
  progress?: number;
  importance?: number;
  urgency?: number;
  deadline?: string;
  last_activity_at?: string;
}

export async function createWorkItem(body: CreateWorkItemPayload): Promise<WorkItem> {
  return request<WorkItem>(`${API_BASE}/work-items/`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface UpdateWorkItemPayload {
  title?: string;
  description?: string;
  status?: string;
  priority?: number;
  progress?: number;
  importance?: number;
  urgency?: number;
  deadline?: string;
  last_activity_at?: string;
  parent_work_id?: string;
}

export async function updateWorkItem(
  itemId: string,
  body: UpdateWorkItemPayload,
): Promise<WorkItem> {
  return request<WorkItem>(`${API_BASE}/work-items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function transitionStatus(itemId: string, status: string): Promise<WorkItem> {
  return request<WorkItem>(`${API_BASE}/work-items/${itemId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export async function deleteWorkItem(itemId: string): Promise<void> {
  await request(`${API_BASE}/work-items/${itemId}`, { method: "DELETE" });
}

export async function executeWorkItem(itemId: string): Promise<WorkItem> {
  return request<WorkItem>(`${API_BASE}/work-items/${itemId}/execute`, {
    method: "POST",
  });
}

export async function decomposeWorkItem(itemId: string): Promise<{ steps: string[] }> {
  return request<{ steps: string[] }>(`${API_BASE}/work-items/${itemId}/decompose`, {
    method: "POST",
  });
}
