/**
 * Goals client — thin adapters over /api/work-items (Phase 4).
 *
 * Keeps the Goal view-model for existing pages while all HTTP goes through
 * the unified work-items surface.
 */

import { API_BASE, request } from "./core";
import type { Goal, GoalAction, GoalEvent, WorkItem } from "./types";
import {
  createWorkItem,
  deleteWorkItem,
  getWorkItem,
  listWorkItems,
  updateWorkItem,
} from "./workItems";

function actionToGoalAction(item: WorkItem, goalId: string): GoalAction {
  return {
    id: item.id,
    goal_id: item.parent_goal_id || goalId,
    title: item.title,
    status: item.status,
    created_at: item.created_at,
    completed_at: item.completed_at,
  };
}

function workItemToGoal(item: WorkItem & { actions?: WorkItem[]; events?: GoalEvent[] }): Goal {
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
    actions: (item.actions || []).map((a) => actionToGoalAction(a, item.id)),
    events: item.events,
  };
}

export async function listGoals(status?: string): Promise<Goal[]> {
  const items = await listWorkItems("goal", status);
  return items.map((item) => workItemToGoal(item));
}

export async function getGoal(goalId: string): Promise<Goal> {
  const item = await getWorkItem(goalId, "actions,events");
  return workItemToGoal(item as WorkItem & { actions?: WorkItem[]; events?: GoalEvent[] });
}

export async function createGoal(body: { title: string; description?: string }): Promise<Goal> {
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
  const item = await updateWorkItem(goalId, {
    ...body,
    description: body.description ?? undefined,
  });
  return workItemToGoal(item);
}

export async function deleteGoal(goalId: string): Promise<void> {
  await deleteWorkItem(goalId);
}

export async function createGoalAction(goalId: string, title: string): Promise<GoalAction> {
  const item = await createWorkItem({
    title,
    work_type: "action",
    parent_goal_id: goalId,
    status: "pending",
  });
  return actionToGoalAction(item, goalId);
}

export async function updateGoalAction(
  goalId: string,
  actionId: string,
  body: { status: string },
): Promise<GoalAction> {
  const item = await updateWorkItem(actionId, body);
  return actionToGoalAction(item, goalId);
}

export async function decomposeGoal(goalId: string): Promise<{ steps: string[] }> {
  return request<{ steps: string[] }>(`${API_BASE}/work-items/${goalId}/decompose`, {
    method: "POST",
  });
}
