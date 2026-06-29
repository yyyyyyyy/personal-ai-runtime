import { useCallback, useEffect, useRef, useState } from "react";
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

interface DashboardState {
  cost: CostSummary | null;
  costByModel: ModelCostItem[];
  tools: ToolSummaryItem[];
  memory: MemoryStats | null;
  health: HealthSnapshot | null;
  notifications: Notification[];
  dashboard: DashboardData | null;
}

export function useDashboard() {
  const [data, setData] = useState<DashboardState>({
    cost: null,
    costByModel: [],
    tools: [],
    memory: null,
    health: null,
    notifications: [],
    dashboard: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const fetchIdRef = useRef(0);
  const addError = useErrorStore((s) => s.addError);

  const fetchData = useCallback(async () => {
    const fetchId = ++fetchIdRef.current;
    setLoading(true);
    setError("");

    try {
      const [costData, modelCostData, toolData, memData, healthData, notifData, dashData] = await Promise.all([
        getCostSummary(7),
        getCostByModel(7),
        getToolSummary(7),
        getMemoryStats(),
        getHealth(),
        listNotifications(10).catch(() => [] as Notification[]),
        getDashboard().catch(() => null),
      ]);

      // Abort if a newer fetch superseded this one
      if (fetchId !== fetchIdRef.current) return;

      setData({
        cost: costData,
        costByModel: modelCostData,
        tools: toolData,
        memory: memData,
        health: healthData,
        notifications: notifData,
        dashboard: dashData,
      });
    } catch (e) {
      if (fetchId !== fetchIdRef.current) return;
      const msg = e instanceof Error ? e.message : "无法连接到后端服务，请确认后端已启动";
      setError(msg);
      addError(msg, "仪表盘");
    } finally {
      if (fetchId === fetchIdRef.current) {
        setLoading(false);
      }
    }
  }, [addError]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { ...data, loading, error, refresh: fetchData };
}
