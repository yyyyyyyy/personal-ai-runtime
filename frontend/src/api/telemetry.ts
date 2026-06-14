/** Telemetry API — cost, tool usage, memory stats, health snapshot. */

import { API_BASE, request } from "./core";
import type { CostSummary, ModelCostItem, ToolSummaryItem, MemoryStats, HealthSnapshot } from "./types";

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
