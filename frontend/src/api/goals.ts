/**
 * Goals API client — migrating toward /api/work-items.
 *
 * CRUD list/create/update/delete go through workItems (work_type=goal).
 * getGoal, actions, and decompose remain on /api/goals (actions + events
 * composition and goal-specific endpoints not yet mirrored on work-items).
 */

import { API_BASE, request } from "./core";
import type { Goal, GoalAction, WorkItem } from "./types";
import {
  createWorkItem,
  deleteWorkItem,
  listWorkItems,
  updateWorkItem,
} from "./workItems";

function workItemToGoal(item: WorkItem): Goal {
  return {
    id: item.id,
    title: item.title,
    description: item.description,
    status: item.status,
    progress: item.progress,
    importance: item.importance,
    urgency: item.urgency,
    deadline: item.deadline,
    parent_id: item.parent_work_id,
    created_at: item.created_at,
    last_activity_at: item.last_activity_at,
  };
}

export async function listGoals(status?: string): Promise<Goal[]> {
  const items = await listWorkItems("goal", status);
  return items.map(workItemToGoal);
}

export async function getGoal(goalId: string): Promise<Goal> {
  // Still /api/goals — embeds actions + events.
  return request<Goal>(`${API_BASE}/goals/${goalId}`);
}

export async function createGoal(body: {
  title: string;
  description?: string;
}): Promise<Goal> {
  const item = await createWorkItem({
    title: body.title,
    description: body.description,
    work_type: "goal",
    status: "active",
  });
  return workItemToGoal(item);
}

export async function updateGoal(
  goalId: string,
  body: Partial<Pick<Goal, "title" | "description" | "status" | "progress">>,
): Promise<Goal> {
  const item = await updateWorkItem(goalId, body);
  return workItemToGoal(item);
}

export async function deleteGoal(goalId: string): Promise<void> {
  await deleteWorkItem(goalId);
}

export async function createGoalAction(goalId: string, title: string): Promise<GoalAction> {
  return request<GoalAction>(`${API_BASE}/goals/${goalId}/actions`, {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export async function updateGoalAction(
  goalId: string,
  actionId: string,
  body: { status: string },
): Promise<GoalAction> {
  return request<GoalAction>(`${API_BASE}/goals/${goalId}/actions/${actionId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function decomposeGoal(goalId: string): Promise<{ steps: string[] }> {
  return request<{ steps: string[] }>(`${API_BASE}/goals/${goalId}/decompose`, {
    method: "POST",
  });
}
