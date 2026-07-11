import { useQuery } from "@tanstack/react-query";
import { getPortrait, type PortraitData } from "../api/portrait";
import { queryKeys } from "./useWsInvalidationBridge";

export function usePortraitQuery() {
  return useQuery<PortraitData>({
    queryKey: queryKeys.portrait,
    queryFn: getPortrait,
    staleTime: 30_000,
    retry: 1,
    retryDelay: 0,
  });
}
