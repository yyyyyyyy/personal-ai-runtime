/** System API — health, LLM providers, MCP status, export/import, dashboard. */

import { API_BASE, ApiError, authHeaders, request } from "./core";
import type { HealthResponse, SystemInfo, LlmProvidersResponse, DashboardData } from "./types";

export async function getSystemHealth(): Promise<HealthResponse> {
  return request<HealthResponse>(`${API_BASE}/system/health`);
}

export async function fetchSystemInfo(): Promise<SystemInfo> {
  return request<SystemInfo>(`${API_BASE}/system/info`);
}

export async function getLlmProviders(): Promise<LlmProvidersResponse> {
  return request<LlmProvidersResponse>(`${API_BASE}/system/llm-providers`);
}

export async function getDashboard(): Promise<DashboardData> {
  return request<DashboardData>(`${API_BASE}/dashboard`);
}

/** Parse plaintext export JSON (tests / programmatic use). Prefer downloadExport for UI. */
export async function exportData(): Promise<Record<string, unknown>> {
  return request(`${API_BASE}/system/export`, {
    method: "POST",
    body: JSON.stringify({ confirm: "EXPORT_ALL_DATA" }),
  });
}

/**
 * Stream plaintext snapshot to a file download without JSON.parse + re-stringify.
 * Response body is already valid snapshot JSON from the server.
 */
export async function downloadExport(filename?: string): Promise<void> {
  const res = await fetch(`${API_BASE}/system/export`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ confirm: "EXPORT_ALL_DATA" }),
  });

  if (res.status === 401) {
    throw new ApiError("认证失败，请检查 AUTH_TOKEN 与 VITE_AUTH_TOKEN 是否一致", 401);
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body.detail || body.message || "";
    } catch {
      // not JSON
    }
    throw new ApiError(detail || `请求失败 (HTTP ${res.status})`, res.status);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename ?? `personal-ai-backup-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function importData(
  data: Record<string, unknown>,
  readOnly = false,
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

export async function exportEncryptedData(
  password: string,
): Promise<{ format: string; data: string }> {
  return request(`${API_BASE}/system/export/encrypted`, {
    method: "POST",
    body: JSON.stringify({ confirm: "EXPORT_ALL_DATA", password }),
  });
}

export async function importEncryptedData(
  data: string,
  password: string,
): Promise<Record<string, unknown>> {
  return request(`${API_BASE}/system/import/encrypted`, {
    method: "POST",
    body: JSON.stringify({ confirm: "DESTROY_AND_IMPORT", data, password }),
  });
}

export async function destroyAllData(): Promise<Record<string, unknown>> {
  // Backend reads confirm from the query string (not JSON body).
  return request(`${API_BASE}/system/data?confirm=${encodeURIComponent("DESTROY_ALL_DATA")}`, {
    method: "DELETE",
  });
}
