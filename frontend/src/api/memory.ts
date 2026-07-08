/** Memory API — CRUD and search. */

import { API_BASE, request } from "./core";
import type { MemoryRow, MemoriesGrouped } from "./types";

export async function listMemoriesGrouped(): Promise<MemoriesGrouped> {
  return request<MemoriesGrouped>(`${API_BASE}/memory/memories/grouped`);
}

export async function searchMemories(q: string, n = 5): Promise<MemoryRow[]> {
  return request<MemoryRow[]>(
    `${API_BASE}/memory/memories/search?q=${encodeURIComponent(q)}&n=${n}`,
  );
}

export async function createMemory(body: {
  content: string;
  category?: string;
}): Promise<{ id: string; status: string }> {
  return request(`${API_BASE}/memory/memories`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteMemory(memoryId: string): Promise<{ status: string }> {
  return request(`${API_BASE}/memory/memories/${memoryId}`, { method: "DELETE" });
}

export async function updateMemory(
  memoryId: string,
  body: { content: string; category?: string },
): Promise<{ status: string }> {
  return request(`${API_BASE}/memory/memories/${memoryId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function ratifyMemory(
  memoryId: string,
): Promise<{ status: string; claim_status: string }> {
  return request(`${API_BASE}/memory/memories/${memoryId}/ratify`, { method: "POST" });
}

export async function rejectMemory(
  memoryId: string,
): Promise<{ status: string; claim_status: string }> {
  return request(`${API_BASE}/memory/memories/${memoryId}/reject`, { method: "POST" });
}

export async function contestMemory(
  memoryId: string,
): Promise<{ status: string; claim_status: string }> {
  return request(`${API_BASE}/memory/memories/${memoryId}/contest`, { method: "POST" });
}

export interface MemoryProvenanceEvent {
  seq: number;
  type: string;
  ts: string;
  actor: string;
  payload: Record<string, unknown>;
  correlation_id: string | null;
}

export interface MemoryProvenance {
  memory_id: string;
  events: MemoryProvenanceEvent[];
}

export async function getMemoryProvenance(memoryId: string): Promise<MemoryProvenance> {
  return request<MemoryProvenance>(`${API_BASE}/memory/memories/${memoryId}/provenance`);
}

export interface MemoryGraphNode {
  id: string;
  content: string;
  category: string;
  confidence: number;
}

export interface MemoryGraphEdge {
  source: string;
  target: string;
  weight: number;
}

export interface MemoryGraph {
  nodes: MemoryGraphNode[];
  edges: MemoryGraphEdge[];
}

export async function getMemoryGraph(limit = 50): Promise<MemoryGraph> {
  return request<MemoryGraph>(`${API_BASE}/memory/graph?limit=${limit}`);
}
