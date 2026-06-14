import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthToken } from "../api/client";

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  content: string;
  created_at: string;
  read?: number;
}

// Type guard for WebSocket notification payload
interface WSNotificationPayload {
  type: string;
  id?: string;
  title?: string;
  content?: string;
  created_at?: string;
}

function isValidNotification(data: unknown): data is WSNotificationPayload {
  return (
    typeof data === "object" &&
    data !== null &&
    "type" in data &&
    typeof (data as Record<string, unknown>)["type"] === "string"
  );
}

function buildWsUrl(): string {
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws`;
  }
  return `ws://${__API_HOST__}:${__API_PORT__}/ws`;
}

function buildWsProtocols(): string[] | undefined {
  const token = getAuthToken();
  return token ? [`auth.${token}`] : undefined;
}

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY_MS = 5000;

export function useNotifications() {
  const [toasts, setToasts] = useState<NotificationItem[]>([]);
  const [liveNotifications, setLiveNotifications] = useState<NotificationItem[]>([]);
  const reconnectCountRef = useRef(0);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Stable ref for dismissToast to avoid unnecessary reconnects
  const dismissToastRef = useRef(dismissToast);
  dismissToastRef.current = dismissToast;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let stopped = false;

    const connect = () => {
      if (stopped || reconnectCountRef.current >= MAX_RECONNECT_ATTEMPTS) return;

      try {
        const protocols = buildWsProtocols();
        ws = protocols
          ? new WebSocket(buildWsUrl(), protocols)
          : new WebSocket(buildWsUrl());

        ws.onmessage = (event) => {
          try {
            const raw = JSON.parse(event.data);
            if (!isValidNotification(raw)) return;
            if (raw.type !== "notification") return;

            const item: NotificationItem = {
              id: raw.id || `live-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              type: raw.type,
              title: raw.title || "通知",
              content: raw.content || "",
              created_at: raw.created_at || new Date().toISOString(),
            };

            setLiveNotifications((prev) => [item, ...prev].slice(0, 20));
            setToasts((prev) => [item, ...prev].slice(0, 3));

            setTimeout(() => {
              dismissToastRef.current(item.id);
            }, 8000);
          } catch {
            // ignore malformed messages
          }
        };

        ws.onopen = () => {
          reconnectCountRef.current = 0;
        };

        ws.onerror = () => {
          // onclose will handle reconnection
        };

        ws.onclose = () => {
          if (!stopped) {
            reconnectCountRef.current += 1;
            if (reconnectCountRef.current < MAX_RECONNECT_ATTEMPTS) {
              reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
            }
          }
        };
      } catch {
        if (!stopped) {
          reconnectCountRef.current += 1;
          if (reconnectCountRef.current < MAX_RECONNECT_ATTEMPTS) {
            reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS * 2);
          }
        }
      }
    };

    connect();

    return () => {
      stopped = true;
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  return { toasts, liveNotifications, dismissToast };
}
