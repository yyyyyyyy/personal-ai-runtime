import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type Notification,
} from "../../api/client";
import NotificationDetailModal from "../notifications/NotificationDetailModal";
import { notificationPreview } from "../../utils/notificationUtils";

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [selected, setSelected] = useState<Notification | null>(null);

  const loadNotifications = async () => {
    try {
      const items = await listNotifications(15);
      setNotifications(items);
    } catch {
      // optional
    }
  };

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 60000);
    return () => clearInterval(interval);
  }, []);

  const unread = notifications.filter((n) => !n.read).length;

  const handleOpenDetail = async (n: Notification) => {
    setOpen(false);
    setSelected(n);
    if (!n.read) {
      try {
        await markNotificationRead(n.id);
        setNotifications((prev) =>
          prev.map((item) => (item.id === n.id ? { ...item, read: 1 } : item)),
        );
        setSelected((prev) => (prev?.id === n.id ? { ...prev, read: 1 } : prev));
      } catch {
        // still show detail
      }
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, read: 1 })));
    } catch {
      // ignore
    }
  };

  return (
    <>
      <div className="relative px-3 pb-2">
        <button
          onClick={() => {
            setOpen(!open);
            if (!open) loadNotifications();
          }}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-gray-800/50 transition-colors"
          aria-label="通知"
        >
          <Bell size={18} />
          <span>通知</span>
          {unread > 0 && (
            <span className="ml-auto bg-emerald-600 text-white text-xs px-1.5 py-0.5 rounded-full min-w-[20px] text-center">
              {unread}
            </span>
          )}
        </button>

        {open && (
          <div className="absolute bottom-full left-2 right-2 mb-1 bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-h-64 overflow-y-auto z-50">
            <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800">
              <span className="text-xs text-gray-500">最近通知</span>
              {unread > 0 && (
                <button
                  type="button"
                  onClick={handleMarkAllRead}
                  className="text-xs text-emerald-400 hover:text-emerald-300"
                >
                  全部已读
                </button>
              )}
            </div>
            {notifications.length === 0 ? (
              <p className="text-xs text-gray-500 p-4 text-center">暂无通知</p>
            ) : (
              notifications.map((n) => (
                <button
                  key={n.id}
                  onClick={() => handleOpenDetail(n)}
                  className={`w-full text-left p-3 hover:bg-gray-800 border-b border-gray-800 last:border-0 ${
                    n.read ? "opacity-60" : ""
                  }`}
                >
                  <p className={`text-sm ${n.read ? "text-gray-400" : "text-emerald-400"}`}>
                    {n.title}
                  </p>
                  <p className="text-xs text-gray-500 mt-1 line-clamp-2">
                    {notificationPreview(n.content)}
                  </p>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      <NotificationDetailModal notification={selected} onClose={() => setSelected(null)} />
    </>
  );
}
