import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getTrustReport } from "../api/trustReport";
import { queryKeys } from "./useWsInvalidationBridge";

const TRUST_STALE_MS = 30_000;

export function useTrustReportQuery() {
  return useQuery({
    queryKey: queryKeys.trustReport,
    queryFn: getTrustReport,
    staleTime: TRUST_STALE_MS,
    retry: 1,
    retryDelay: 0,
  });
}

export function useInvalidateTrustReport() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: queryKeys.trustReport });
}
