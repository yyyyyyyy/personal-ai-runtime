/** Connectors / MCP marketplace API. */

import { API_BASE, request } from "./core";

export interface McpRegistryServer {
  name: string;
  description: string;
  category: string;
  env_vars: Record<string, string>;
}

export async function listMcpRegistry(): Promise<McpRegistryServer[]> {
  const data = await request<{ servers: McpRegistryServer[] }>(
    `${API_BASE}/connectors/registry`,
  );
  return data.servers ?? [];
}

export async function installMcpConnector(
  name: string,
): Promise<{ ok: boolean; message: string }> {
  return request(`${API_BASE}/connectors/install`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}
