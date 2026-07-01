import { useNavigate } from "react-router-dom";
import type { Notification } from "../../api/client";
import Button from "../ui/Button";
import { notificationTargetPath, notificationTypeLabel } from "../../utils/notificationRoutes";
import { notificationPreview } from "../../utils/notificationUtils";

interface Props {
  notification: Notification | null;
  onClose: () => void;
}

function formatTime(value: string): string {
  try {
    return new Date(value).toLocaleString("zh-CN");
  } catch {
    return value;
  }
}

export default function NotificationDetailModal({ notification, onClose }: Props) {
  const navigate = useNavigate();

  if (!notification) return null;

  const target = notificationTargetPath(notification.type);
  const displayContent = notificationPreview(notification.content);

  const handleNavigate = () => {
    onClose();
    if (target) navigate(target);
  };

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl max-w-lg w-full shadow-xl flex flex-col max-h-[80vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 pt-5 pb-3 border-b border-gray-800">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <span className="inline-block text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400 mb-2">
                {notificationTypeLabel(notification.type)}
              </span>
              <h3 className="text-lg font-semibold text-gray-100 break-words">
                {notification.title}
              </h3>
              <p className="text-xs text-gray-500 mt-1">{formatTime(notification.created_at)}</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-gray-500 hover:text-gray-300 text-xl leading-none shrink-0"
              aria-label="关闭"
            >
              ×
            </button>
          </div>
        </div>

        <div className="px-5 py-4 overflow-y-auto flex-1">
          <pre className="text-sm text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">
            {displayContent || "（无详细内容）"}
          </pre>
        </div>

        <div className="px-5 py-4 border-t border-gray-800 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            关闭
          </Button>
          {target && (
            <Button size="sm" onClick={handleNavigate}>
              查看相关页面
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
