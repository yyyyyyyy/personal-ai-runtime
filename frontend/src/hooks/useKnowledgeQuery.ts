import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listKnowledgeDocuments, type KnowledgeDocument } from "../api/knowledge";
import { queryKeys } from "./useWsInvalidationBridge";

export function useKnowledgeDocumentsQuery() {
  return useQuery<KnowledgeDocument[]>({
    queryKey: queryKeys.knowledge,
    queryFn: () => listKnowledgeDocuments(),
    staleTime: 30_000,
  });
}

export function useInvalidateKnowledge() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.knowledge });
  };
}
