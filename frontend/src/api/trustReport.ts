/** Trust Report API — aggregates trust-related data for Phase 1 Trust Moat. */

import { API_BASE, request } from "./core";
import type { EnrichedApproval, SystemInfo } from "./types";
import { listEnrichedPendingApprovals } from "./approvals";
import { fetchSystemInfo, getDashboard } from "./system";
import { getCostSummary, getCostByModel, getToolSummary, getMemoryStats, getHealth } from "./telemetry";
import type { CostSummary, ModelCostItem, ToolSummaryItem, MemoryStats, HealthSnapshot } from "./types";
import type { DashboardData } from "./types";

export interface TrustReportData {
  system: SystemInfo;
  approvals: EnrichedApproval[];
  cost: CostSummary;
  costByModel: ModelCostItem[];
  tools: ToolSummaryItem[];
  memory: MemoryStats;
  health: HealthSnapshot;
  dashboard: DashboardData | null;
}

export async function getTrustReport(): Promise<TrustReportData> {
  const [system, approvals, cost, costByModel, tools, memory, health, dashboard] =
    await Promise.all([
      fetchSystemInfo(),
      listEnrichedPendingApprovals(),
      getCostSummary(7),
      getCostByModel(7),
      getToolSummary(7),
      getMemoryStats(),
      getHealth(),
      getDashboard().catch(() => null),
    ]);

  return { system, approvals, cost, costByModel, tools, memory, health, dashboard };
}
