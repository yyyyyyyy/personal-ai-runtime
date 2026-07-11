/**
 * Goals list + detail queries. Mutations invalidate queryKeys.goals so the
 * WS bridge (and local invalidate after writes) keep the UI fresh.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listGoals, getGoal, type Goal } from "../api/client";
import { queryKeys } from "./useWsInvalidationBridge";

export function useGoalsQuery() {
  return useQuery<Goal[]>({
    queryKey: queryKeys.goals,
    queryFn: () => listGoals(),
    staleTime: 15_000,
  });
}

export function useGoalQuery(goalId: string | undefined) {
  return useQuery<Goal>({
    queryKey: [...queryKeys.goals, goalId] as const,
    queryFn: () => getGoal(goalId!),
    enabled: Boolean(goalId),
    staleTime: 10_000,
    retry: (count, err) => {
      // Don't retry 404 — surface as not-found UI.
      if (
        err &&
        typeof err === "object" &&
        "status" in err &&
        (err as { status: number }).status === 404
      ) {
        return false;
      }
      return count < 1;
    },
  });
}

export function useInvalidateGoals() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.goals });
  };
}
