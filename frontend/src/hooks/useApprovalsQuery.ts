import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listEnrichedPendingApprovals, type EnrichedApproval } from "../api/client";
import { queryKeys } from "./useWsInvalidationBridge";

export function useApprovalsQuery() {
  return useQuery<EnrichedApproval[]>({
    queryKey: queryKeys.approvals,
    queryFn: () => listEnrichedPendingApprovals(),
    staleTime: 10_000,
  });
}

export function useInvalidateApprovals() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.approvals });
  };
}
