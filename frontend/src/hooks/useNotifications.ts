import { useCallback, useEffect, useState } from "react";

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  content: string;
  created_at: string;
  read?: number;
}

const WS_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000/ws`
    : "ws://localhost:8000/ws";

export function useNotifications() {
  const [toasts, setToasts] = useState<NotificationItem[]>([]);
  const [liveNotifications, setLiveNotifications] = useState<NotificationItem[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      try {
        ws = new WebSocket(WS_URL);
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === "notification") {
              const item: NotificationItem = {
                id: data.id || `live-${Date.now()}`,
                type: data.type,
                title: data.title || "通知",
                content: data.content || "",
                created_at: data.created_at || new Date().toISOString(),
              };
              setLiveNotifications((prev) => [item, ...prev].slice(0, 20));
              setToasts((prev) => [item, ...prev].slice(0, 3));
              setTimeout(() => dismissToast(item.id), 8000);
            }
          } catch {
            // ignore malformed messages
          }
        };
        ws.onclose = () => {
          reconnectTimer = setTimeout(connect, 5000);
        };
      } catch {
        reconnectTimer = setTimeout(connect, 10000);
      }
    };

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [dismissToast]);

  return { toasts, liveNotifications, dismissToast };
}
