/**
 * Notification list for the sidebar bell. Invalidated by WS `notification`
 * events via useWsInvalidationBridge — no setInterval polling.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listNotifications, type Notification } from "../api/client";
import { queryKeys } from "./useWsInvalidationBridge";

export function useNotificationsQuery(limit = 15) {
  return useQuery<Notification[]>({
    queryKey: [...queryKeys.notifications, limit] as const,
    queryFn: () => listNotifications(limit),
    staleTime: 30_000,
  });
}

export function useInvalidateNotifications() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.notifications });
  };
}
