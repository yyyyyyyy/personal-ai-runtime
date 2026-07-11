/**
 * Query invalidation hub — converts WS events into TanStack Query
 * cache invalidations so the UI updates without setTimeout polling.
 *
 * Mounted once at the app root (see AppEventBridge in Layout). The
 * WebSocket itself is owned by useNotifications; we subscribe to its
 * raw messages here via a small event-target shim.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

// Keys are intentionally broad; concrete queries opt in via queryKey prefixes.
export const queryKeys = {
  memories: ["memories"] as const,
  memoriesGrouped: ["memories", "grouped"] as const,
  goals: ["goals"] as const,
  inbox: ["inbox"] as const,
  dashboard: ["dashboard"] as const,
  approvals: ["approvals"] as const,
  knowledge: ["knowledge"] as const,
  timeline: ["timeline"] as const,
  mcpRegistry: ["mcpRegistry"] as const,
} as const;

// Lightweight pub/sub so useNotifications (which owns the WS) can forward
// non-notification payloads here without prop-drilling.
type Listener = (payload: unknown) => void;
const listeners: Set<Listener> = new Set();

export function dispatchWsEvent(payload: unknown): void {
  for (const l of listeners) {
    try {
      l(payload);
    } catch {
      // listener errors must never break other listeners
    }
  }
}

/**
 * Hook: subscribe WS payloads to React Query invalidations.
 * Call once near the root (inside QueryClientProvider).
 */
export function useWsInvalidationBridge(): void {
  const qc = useQueryClient();

  useEffect(() => {
    const handler: Listener = (raw) => {
      if (!raw || typeof raw !== "object") return;
      const evt = raw as { type?: string };
      switch (evt.type) {
        case "memory_changed":
          // Memories list / grouped view / dashboard counters depend on this.
          void qc.invalidateQueries({ queryKey: queryKeys.memories });
          void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
          break;
        case "notification":
          // Notifications arrive via toast; refresh dashboard counters.
          void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
          break;
        default:
          // Unknown event types are ignored — explicit opt-in only.
          break;
      }
    };
    listeners.add(handler);
    return () => {
      listeners.delete(handler);
    };
  }, [qc]);
}
