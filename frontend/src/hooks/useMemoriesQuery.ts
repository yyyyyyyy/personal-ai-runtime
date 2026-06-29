/**
 * useMemoriesQuery — TanStack Query-backed memories fetcher.
 *
 * Replaces the ad-hoc useState + setTimeout pattern in ChatView. Cache
 * invalidation is driven by WS `memory_changed` events (see
 * useWsInvalidationBridge), so consumers never need to poll.
 */
import { useQuery } from "@tanstack/react-query";
import { listMemoriesGrouped, type MemoryRow } from "../api/client";
import { queryKeys } from "./useWsInvalidationBridge";

export interface MemoriesGroupedResult {
  /** All memories, newest-first. Use `.length` for the real total. */
  memories: MemoryRow[];
  /** Convenience slice of the 3 most recent for welcome-screen display. */
  recent: MemoryRow[];
}

export function useMemoriesGroupedQuery() {
  return useQuery<MemoriesGroupedResult>({
    queryKey: queryKeys.memoriesGrouped,
    queryFn: async () => {
      const data = await listMemoriesGrouped();
      const memories = (data.memories ?? []).slice().sort((a, b) => {
        const at = new Date(a.created_at ?? 0).getTime();
        const bt = new Date(b.created_at ?? 0).getTime();
        return bt - at;
      });
      return { memories, recent: memories.slice(0, 3) };
    },
    // Memories change via background extraction; keep reasonably fresh even
    // if a WS event is missed.
    staleTime: 10_000,
  });
}
