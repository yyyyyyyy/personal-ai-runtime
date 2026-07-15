/** Trust Report API — aggregates trust-related data. */

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
  governance: GovernanceSummary | null;
  dashboard: DashboardData | null;
  memoryIndexRepairs: MemoryIndexRepairsResponse;
}

const EMPTY_COST: CostSummary = {
  total_calls: 0,
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  total_cost: 0,
  avg_latency_ms: 0,
  failed_calls: 0,
};

const EMPTY_MEMORY: MemoryStats = {
  total_memories: 0,
  categories: {},
  recent_7d: 0,
};

const EMPTY_HEALTH: HealthSnapshot = {
  task_queue_length: 0,
  llm_failure_rate_24h: 0,
  tool_failure_rate_24h: 0,
};

const EMPTY_REPAIRS: MemoryIndexRepairsResponse = {
  pending: 0,
  failed_permanent: 0,
  items: [],
};

async function soft<T>(promise: Promise<T>, fallback: T): Promise<T> {
  try {
    return await promise;
  } catch {
    return fallback;
  }
}

export async function getTrustReport(): Promise<TrustReportData> {
  // system is required for the page shell; everything else soft-fails so one
  // telemetry outage cannot blank the whole trust tab.
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
    soft(listEnrichedPendingApprovals(), [] as EnrichedApproval[]),
    soft(getCostSummary(7), EMPTY_COST),
    soft(getCostByModel(7), [] as ModelCostItem[]),
    soft(getToolSummary(7), [] as ToolSummaryItem[]),
    soft(getMemoryStats(), EMPTY_MEMORY),
    soft(getHealth(), EMPTY_HEALTH),
    soft(getGovernanceSummary(7), null),
    soft(getDashboard(), null),
    soft(getMemoryIndexRepairs("all"), EMPTY_REPAIRS),
  ]);

  return {
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
  };
}
