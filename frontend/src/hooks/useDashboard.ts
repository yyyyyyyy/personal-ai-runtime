import { useCallback, useEffect, useRef } from "react";
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
 *
 * Soft failures (telemetry / notifications) toast but do not blank the page.
 * Full-page error only when we have no useful data after load settles.
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
    queryFn: () => listNotifications(10),
    refetchInterval: DASHBOARD_STALE_MS,
    staleTime: 30_000,
    retry: 1,
  });

  const dashboard = useQuery<DashboardData>({
    queryKey: queryKeys.dashboard,
    queryFn: getDashboard,
    refetchInterval: DASHBOARD_STALE_MS,
    staleTime: 30_000,
    retry: 1,
  });

  const queries = [cost, costByModel, tools, memory, health, notifications, dashboard];
  const anyLoading = queries.some((q) => q.isLoading);
  const hasAnyData = queries.some((q) => q.data !== undefined);
  const errors = queries.map((q) => q.error).filter(Boolean);

  // Initial spinner only until at least one subset arrives (or all settle empty).
  const loading = anyLoading && !hasAnyData;

  // Full-page error only when every query failed and nothing rendered.
  const fatalError =
    !loading && !hasAnyData && errors.length > 0
      ? errors[0] instanceof Error
        ? errors[0].message
        : "无法连接到后端服务，请确认后端已启动"
      : null;

  const softErrorMsg =
    !loading && hasAnyData && errors.length > 0
      ? errors[0] instanceof Error
        ? errors[0].message
        : "部分仪表盘数据加载失败"
      : fatalError;

  const lastErrorRef = useRef<string | null>(null);
  useEffect(() => {
    if (!softErrorMsg) {
      lastErrorRef.current = null;
      return;
    }
    if (lastErrorRef.current === softErrorMsg) return;
    lastErrorRef.current = softErrorMsg;
    addError(softErrorMsg, "仪表盘");
  }, [softErrorMsg, addError]);

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
    error: fatalError ?? "",
    refresh,
  };
}
