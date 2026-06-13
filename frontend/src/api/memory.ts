/** Memory API — CRUD and search. */

import { API_BASE, request } from "./core";
import type { MemoryRow, MemoriesGrouped } from "./types";

export async function listMemoriesGrouped(): Promise<MemoriesGrouped> {
  return request<MemoriesGrouped>(`${API_BASE}/memory/memories/grouped`);
}

export async function searchMemories(q: string, n = 5): Promise<MemoryRow[]> {
  return request<MemoryRow[]>(
    `${API_BASE}/memory/memories/search?q=${encodeURIComponent(q)}&n=${n}`
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
