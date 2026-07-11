import { useInfiniteQuery } from "@tanstack/react-query";
import { listTimelineEvents } from "../api/timeline";
import { queryKeys } from "./useWsInvalidationBridge";

export function useTimelineInfiniteQuery() {
  return useInfiniteQuery({
    queryKey: queryKeys.timeline,
    queryFn: ({ pageParam }) => listTimelineEvents(pageParam, 30),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
    staleTime: 30_000,
  });
}
