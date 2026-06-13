/** Knowledge API — document import, search (RAG). */

import { API_BASE, request, getAuthToken, ApiError } from "./core";
import type { KnowledgeDocument } from "./types";

export async function listKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  return request<KnowledgeDocument[]>(`${API_BASE}/knowledge/documents`);
}

export async function importKnowledgeDocument(body: {
  title: string;
  content: string;
}): Promise<{ id: string; title: string; chunk_count: number; status: string }> {
  return request(`${API_BASE}/knowledge/documents`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function uploadKnowledgeDocument(
  file: File
): Promise<{ id: string; title: string; chunk_count: number; status: string }> {
  const form = new FormData();
  form.append("file", file);
  const headers: Record<string, string> = {};
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}/knowledge/documents/upload`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body.detail || "";
    } catch {
      // ignore
    }
    throw new ApiError(detail || `上传失败 (HTTP ${res.status})`, res.status);
  }
  return res.json();
}

export async function deleteKnowledgeDocument(
  docId: string
): Promise<{ status: string }> {
  return request(`${API_BASE}/knowledge/documents/${docId}`, { method: "DELETE" });
}

export async function searchKnowledge(
  q: string,
  n = 5
): Promise<{ query: string; results: Array<{ content: string; metadata?: Record<string, unknown> }> }> {
  return request(
    `${API_BASE}/knowledge/search?q=${encodeURIComponent(q)}&n=${n}`
  );
}
