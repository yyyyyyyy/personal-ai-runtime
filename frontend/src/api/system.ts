/** System API — health, LLM providers, MCP status, export/import, dashboard. */

import { API_BASE, request } from "./core";
import type {
  HealthResponse,
  SystemInfo,
  LlmProvidersResponse,
  McpStatusResponse,
  DashboardData,
} from "./types";

export async function getSystemHealth(): Promise<HealthResponse> {
  return request<HealthResponse>(`${API_BASE}/system/health`);
}

export async function fetchSystemInfo(): Promise<SystemInfo> {
  return request<SystemInfo>(`${API_BASE}/system/info`);
}

export async function getLlmProviders(): Promise<LlmProvidersResponse> {
  return request<LlmProvidersResponse>(`${API_BASE}/system/llm-providers`);
}

export async function getMcpStatus(): Promise<McpStatusResponse> {
  return request<McpStatusResponse>(`${API_BASE}/system/mcp-status`);
}

export async function getDashboard(): Promise<DashboardData> {
  return request<DashboardData>(`${API_BASE}/dashboard`);
}

export async function exportData(): Promise<Record<string, unknown>> {
  return request(`${API_BASE}/system/export`, {
    method: "POST",
    body: JSON.stringify({ confirm: "EXPORT_ALL_DATA" }),
  });
}

export async function importData(
  data: Record<string, unknown>,
  readOnly = false
): Promise<Record<string, unknown>> {
  const body: Record<string, unknown> = { data, read_only: readOnly };
  if (!readOnly) {
    body.confirm = "DESTROY_AND_IMPORT";
  }
  return request(`${API_BASE}/system/import`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
