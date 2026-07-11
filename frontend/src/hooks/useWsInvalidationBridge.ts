/**
 * Query invalidation hub — converts WS events into TanStack Query
 * cache invalidations so the UI updates without setTimeout polling.
 *
 * Mounted once at the app root (see AppEventBridge in Layout). The
 * WebSocket itself is owned by useNotifications; we subscribe to its
 * raw messages here via a small event-target shim.
 */
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

// Keys are intentionally broad; concrete queries opt in via queryKey prefixes.
export const queryKeys = {
  memories: ["memories"] as const,
  memoriesGrouped: ["memories", "grouped"] as const,
  goals: ["goals"] as const,
  inbox: ["inbox"] as const,
  dashboard: ["dashboard"] as const,
  trustReport: ["trustReport"] as const,
  settingsCore: ["settings", "core"] as const,
  settingsHealth: ["settings", "health"] as const,
  capabilityPolicy: ["settings", "capabilityPolicy"] as const,
  promptConfig: ["settings", "prompt"] as const,
  portrait: ["portrait"] as const,
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

function invalidate(qc: QueryClient, key: readonly unknown[]): void {
  void qc.invalidateQueries({ queryKey: key });
}

/** Apply WS payload → Query invalidations. Exported for unit tests. */
export function applyWsInvalidation(qc: QueryClient, raw: unknown): void {
  if (!raw || typeof raw !== "object") return;
  const evt = raw as { type?: string; notification_type?: string };
  switch (evt.type) {
    case "memory_changed":
      invalidate(qc, queryKeys.memories);
      invalidate(qc, queryKeys.dashboard);
      invalidate(qc, queryKeys.portrait);
      invalidate(qc, queryKeys.trustReport);
      invalidate(qc, queryKeys.timeline);
      break;
    case "approval_changed":
      invalidate(qc, queryKeys.approvals);
      invalidate(qc, queryKeys.trustReport);
      invalidate(qc, queryKeys.dashboard);
      break;
    case "notification": {
      invalidate(qc, queryKeys.dashboard);
      invalidate(qc, queryKeys.trustReport);
      const ntype = (evt.notification_type || "").toLowerCase();
      if (ntype.includes("inbox") || ntype.includes("email")) {
        invalidate(qc, queryKeys.inbox);
      }
      if (ntype.includes("goal")) {
        invalidate(qc, queryKeys.goals);
      }
      break;
    }
    default:
      break;
  }
}

/**
 * Hook: subscribe WS payloads to React Query invalidations.
 * Call once near the root (inside QueryClientProvider).
 */
export function useWsInvalidationBridge(): void {
  const qc = useQueryClient();

  useEffect(() => {
    const handler: Listener = (raw) => applyWsInvalidation(qc, raw);
    listeners.add(handler);
    return () => {
      listeners.delete(handler);
    };
  }, [qc]);
}
