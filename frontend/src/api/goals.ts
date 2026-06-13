/** Goals API — goals and actions CRUD. */

import { API_BASE, request } from "./core";
import type { Goal, GoalAction } from "./types";

export async function listGoals(status?: string): Promise<Goal[]> {
  const url = status
    ? `${API_BASE}/goals/?status=${encodeURIComponent(status)}`
    : `${API_BASE}/goals/`;
  return request<Goal[]>(url);
}

export async function getGoal(goalId: string): Promise<Goal> {
  return request<Goal>(`${API_BASE}/goals/${goalId}`);
}

export async function createGoal(body: {
  title: string;
  description?: string;
}): Promise<Goal> {
  return request<Goal>(`${API_BASE}/goals/`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateGoal(
  goalId: string,
  body: Partial<Pick<Goal, "title" | "description" | "status" | "progress">>
): Promise<Goal> {
  return request<Goal>(`${API_BASE}/goals/${goalId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function createGoalAction(
  goalId: string,
  title: string
): Promise<GoalAction> {
  return request<GoalAction>(`${API_BASE}/goals/${goalId}/actions`, {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export async function updateGoalAction(
  goalId: string,
  actionId: string,
  body: { status: string }
): Promise<GoalAction> {
  return request<GoalAction>(`${API_BASE}/goals/${goalId}/actions/${actionId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
