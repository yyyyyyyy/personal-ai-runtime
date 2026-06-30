import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getCostSummary,
  getCostByModel,
  getToolSummary,
  getMemoryStats,
  getHealth,
  listNotifications,
  getDashboard,
  type CostSummary,
  type ModelCostItem,
  type ToolSummaryItem,
  type MemoryStats,
  type HealthSnapshot,
  type Notification,
  type DashboardData,
} from "../api/client";
import { useErrorStore } from "../stores/errorStore";
import { queryKeys } from "./useWsInvalidationBridge";

/**
 * Dashboard data — decomposed into independent TanStack Query hooks
 * so each subset is independently cached and invalidated by the
 * WebSocket invalidation bridge (useWsInvalidationBridge).
 */

const DASHBOARD_STALE_MS = 60_000; // 1-minute refetch interval

export function useDashboard() {
  const addError = useErrorStore((s) => s.addError);

  const cost = useQuery<CostSummary>({
    queryKey: ["telemetry", "costSummary"],
    queryFn: () => getCostSummary(7),
    refetchInterval: DASHBOARD_STALE_MS,
    staleTime: 30_000,
    retry: 1,
  });

  const costByModel = useQuery<ModelCostItem[]>({
    queryKey: ["telemetry", "costByModel"],
    queryFn: () => getCostByModel(7),
    refetchInterval: DASHBOARD_STALE_MS,
    staleTime: 30_000,
    retry: 1,
  });

  const tools = useQuery<ToolSummaryItem[]>({
    queryKey: ["telemetry", "toolSummary"],
    queryFn: () => getToolSummary(7),
    refetchInterval: DASHBOARD_STALE_MS,
    staleTime: 30_000,
    retry: 1,
  });

  const memory = useQuery<MemoryStats>({
    queryKey: ["telemetry", "memoryStats"],
    queryFn: () => getMemoryStats(),
    refetchInterval: DASHBOARD_STALE_MS,
    staleTime: 30_000,
    retry: 1,
  });

  const health = useQuery<HealthSnapshot>({
    queryKey: ["telemetry", "health"],
    queryFn: () => getHealth(),
    refetchInterval: DASHBOARD_STALE_MS,
    staleTime: 30_000,
    retry: 1,
  });

  const notifications = useQuery<Notification[]>({
    queryKey: ["notifications", "dashboard"],
    queryFn: () => listNotifications(10).catch(() => [] as Notification[]),
    refetchInterval: DASHBOARD_STALE_MS,
    staleTime: 30_000,
    retry: 1,
  });

  const dashboard = useQuery<DashboardData | null>({
    queryKey: queryKeys.dashboard,
    queryFn: () => getDashboard().catch(() => null),
    refetchInterval: DASHBOARD_STALE_MS,
    staleTime: 30_000,
    retry: 1,
  });

  // Aggregate loading/error states
  const loading =
    cost.isLoading ||
    costByModel.isLoading ||
    tools.isLoading ||
    memory.isLoading ||
    health.isLoading ||
    notifications.isLoading ||
    dashboard.isLoading;

  const errors = [
    cost.error, costByModel.error, tools.error,
    memory.error, health.error, notifications.error, dashboard.error,
  ].filter(Boolean);

  if (errors.length > 0 && !loading) {
    const msg = errors[0] instanceof Error
      ? (errors[0] as Error).message
      : "无法连接到后端服务，请确认后端已启动";
    addError(msg, "仪表盘");
  }

  const refresh = useCallback(() => {
    cost.refetch();
    costByModel.refetch();
    tools.refetch();
    memory.refetch();
    health.refetch();
    notifications.refetch();
    dashboard.refetch();
  }, [cost, costByModel, tools, memory, health, notifications, dashboard]);

  return {
    cost: cost.data ?? null,
    costByModel: costByModel.data ?? [],
    tools: tools.data ?? [],
    memory: memory.data ?? null,
    health: health.data ?? null,
    notifications: notifications.data ?? [],
    dashboard: dashboard.data ?? null,
    loading,
    error: errors.length > 0 ? String(errors[0]) : "",
    refresh,
  };
}
