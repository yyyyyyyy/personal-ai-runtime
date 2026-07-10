/** Trust Report API — aggregates trust-related data for Phase 1 Trust Moat. */

import type { EnrichedApproval, SystemInfo } from "./types";
import { listEnrichedPendingApprovals } from "./approvals";
import { fetchSystemInfo, getDashboard } from "./system";
import {
  getCostSummary,
  getCostByModel,
  getToolSummary,
  getMemoryStats,
  getHealth,
  getGovernanceSummary,
  getMemoryIndexRepairs,
} from "./telemetry";
import type {
  CostSummary,
  ModelCostItem,
  ToolSummaryItem,
  MemoryStats,
  HealthSnapshot,
} from "./types";
import type { DashboardData } from "./types";
import type { GovernanceSummary, MemoryIndexRepairsResponse } from "./telemetry";

export interface TrustReportData {
  system: SystemInfo;
  approvals: EnrichedApproval[];
  cost: CostSummary;
  costByModel: ModelCostItem[];
  tools: ToolSummaryItem[];
  memory: MemoryStats;
  health: HealthSnapshot;
  governance: GovernanceSummary;
  dashboard: DashboardData | null;
  memoryIndexRepairs: MemoryIndexRepairsResponse;
}

export async function getTrustReport(): Promise<TrustReportData> {
  const [
    system,
    approvals,
    cost,
    costByModel,
    tools,
    memory,
    health,
    governance,
    dashboard,
    memoryIndexRepairs,
  ] = await Promise.all([
    fetchSystemInfo(),
    listEnrichedPendingApprovals(),
    getCostSummary(7),
    getCostByModel(7),
    getToolSummary(7),
    getMemoryStats(),
    getHealth(),
    getGovernanceSummary(7).catch(() => null),
    getDashboard().catch(() => null),
    getMemoryIndexRepairs("all").catch(() => ({
      pending: 0,
      failed_permanent: 0,
      items: [],
    })),
  ]);

  return {
    system,
    approvals,
    cost,
    costByModel,
    tools,
    memory,
    health,
    governance: governance!,
    dashboard,
    memoryIndexRepairs,
  };
}
