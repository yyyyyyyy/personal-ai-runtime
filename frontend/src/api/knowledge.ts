/** Knowledge base API — documents, upload, search. */

import { API_BASE, request, requestFormData } from "./core";

export interface KnowledgeDocument {
  id: string;
  filename: string;
  size: number;
  chunks: number;
  uploaded_at: string;
}

export interface KnowledgeSearchResult {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
  distance: number;
}

export async function listKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  const data = await request<{ documents: KnowledgeDocument[] }>(
    `${API_BASE}/knowledge/documents`,
  );
  return data.documents ?? [];
}

export async function uploadKnowledgeDocument(file: File): Promise<unknown> {
  const formData = new FormData();
  formData.append("file", file);
  return requestFormData(`${API_BASE}/knowledge/upload`, formData);
}

export async function deleteKnowledgeDocument(id: string): Promise<void> {
  await request<void>(`${API_BASE}/knowledge/documents/${id}`, { method: "DELETE" });
}

export async function searchKnowledge(
  query: string,
  nResults = 5,
): Promise<KnowledgeSearchResult[]> {
  const data = await request<{ results: KnowledgeSearchResult[] }>(
    `${API_BASE}/knowledge/search?query=${encodeURIComponent(query)}&n_results=${nResults}`,
  );
  return data.results ?? [];
}
