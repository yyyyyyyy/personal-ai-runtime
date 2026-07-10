/** Telemetry API — cost, tool usage, memory stats, health snapshot. */

import { API_BASE, request } from "./core";
import type {
  CostSummary,
  ModelCostItem,
  ToolSummaryItem,
  MemoryStats,
  HealthSnapshot,
} from "./types";

export async function getCostSummary(days = 7): Promise<CostSummary> {
  return request<CostSummary>(`${API_BASE}/telemetry/cost/summary?days=${days}`);
}

export async function getCostByModel(days = 7): Promise<ModelCostItem[]> {
  return request<ModelCostItem[]>(`${API_BASE}/telemetry/cost/by-model?days=${days}`);
}

export async function getToolSummary(days = 7): Promise<ToolSummaryItem[]> {
  return request<ToolSummaryItem[]>(`${API_BASE}/telemetry/tool-summary?days=${days}`);
}

export async function getMemoryStats(): Promise<MemoryStats> {
  return request<MemoryStats>(`${API_BASE}/telemetry/memory/stats`);
}

export async function getHealth(): Promise<HealthSnapshot> {
  return request<HealthSnapshot>(`${API_BASE}/telemetry/health`);
}

export interface GovernanceSummary {
  window_days: number;
  tools_invoked: number;
  tools_denied: number;
  tools_deferred: number;
  approvals_requested: number;
  approvals_approved: number;
  approvals_rejected: number;
  approvals_expired: number;
  taint_elevated: number;
  by_tool: Record<string, number>;
  denied_tools: Record<string, number>;
}

export async function getGovernanceSummary(days = 7): Promise<GovernanceSummary> {
  return request<GovernanceSummary>(`${API_BASE}/telemetry/governance?days=${days}`);
}

export interface MemoryIndexRepairItem {
  id: number;
  aggregate_id: string;
  event_type: string;
  event_seq: number;
  error: string | null;
  retry_count: number;
  status: string;
  created_at: string;
  last_retry_at: string | null;
}

export interface MemoryIndexRepairsResponse {
  pending: number;
  failed_permanent: number;
  items: MemoryIndexRepairItem[];
}

export async function getMemoryIndexRepairs(
  status: "all" | "pending" | "failed_permanent" = "all",
): Promise<MemoryIndexRepairsResponse> {
  return request<MemoryIndexRepairsResponse>(
    `${API_BASE}/telemetry/memory-index-repairs?status=${status}`,
  );
}

export async function retryMemoryIndexRepair(repairId: number): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`${API_BASE}/telemetry/memory-index-repairs/${repairId}/retry`, {
    method: "POST",
  });
}
