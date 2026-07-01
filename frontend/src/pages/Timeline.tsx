import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Clock, Loader2 } from "lucide-react";
import { API_BASE, request } from "../api/core";
import type { Notification } from "../api/types";

interface TimelineEvent {
  id: string;
  seq: number;
  type: string;
  description: string;
  actor: string;
  ts: string;
  payload_snippet: Record<string, string>;
}

interface TimelineResponse {
  items: TimelineEvent[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  icons: Record<string, string>;
}

const ICON_LABELS: Record<string, { icon: string; color: string }> = {
  target: { icon: "🎯", color: "text-amber-400" },
  "check-circle": { icon: "✅", color: "text-emerald-400" },
  check: { icon: "☑️", color: "text-emerald-400" },
  brain: { icon: "🧠", color: "text-indigo-400" },
  lightbulb: { icon: "💡", color: "text-yellow-400" },
  "message-square": { icon: "💬", color: "text-blue-400" },
  zap: { icon: "⚡", color: "text-orange-400" },
  shield: { icon: "🛡️", color: "text-red-400" },
  "shield-check": { icon: "✅", color: "text-emerald-400" },
  mail: { icon: "📧", color: "text-blue-400" },
  clock: { icon: "⏰", color: "text-gray-400" },
  bell: { icon: "🔔", color: "text-amber-400" },
  play: { icon: "▶️", color: "text-emerald-400" },
};

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return `${d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`;
  } else if (diffDays === 1) {
    return "昨天";
  } else if (diffDays < 7) {
    return `${diffDays} 天前`;
  } else {
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  }
}

function groupByDay(events: TimelineEvent[]): Record<string, TimelineEvent[]> {
  const groups: Record<string, TimelineEvent[]> = {};
  for (const event of events) {
    const d = new Date(event.ts);
    const key = d.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
    if (!groups[key]) groups[key] = [];
    groups[key].push(event);
  }
  return groups;
}

export default function TimelinePage() {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [icons, setIcons] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  const fetchEvents = useCallback(async (pageNum: number, append = false) => {
    if (append) {
      setLoadingMore(true);
    } else {
      setLoading(true);
    }
    setError("");

    try {
      const data = await request<TimelineResponse>(
        `${API_BASE}/timeline/events?page=${pageNum}&page_size=30`,
      );
      if (append) {
        setEvents((prev) => [...prev, ...data.items]);
      } else {
        setEvents(data.items);
      }
      setIcons(data.icons);
      setHasMore(data.has_more);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "加载失败";
      setError(msg);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents(1);
  }, [fetchEvents]);

  const loadMore = () => {
    if (loadingMore || !hasMore) return;
    const nextPage = page + 1;
    setPage(nextPage);
    fetchEvents(nextPage, true);
  };

  const groupedEvents = groupByDay(events);
  const dayKeys = Object.keys(groupedEvents);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={24} className="text-gray-400 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="text-gray-500 mb-2">
            <Clock size={32} className="mx-auto mb-2" />
          </div>
          <div className="text-gray-400 mb-4">{error}</div>
          <button
            onClick={() => fetchEvents(1)}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm transition-colors"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-200">人生时间线</h2>
            <p className="text-sm text-gray-500 mt-0.5">你的 AI 记录的一切</p>
          </div>
        </div>

        {dayKeys.length === 0 ? (
          <div className="text-center py-16">
            <Clock size={48} className="mx-auto mb-4 text-gray-700" />
            <p className="text-gray-500">还没有任何事件</p>
            <p className="text-gray-600 text-sm mt-1">
              开始使用 AI 对话或创建目标后，这里就会出现你的数据足迹
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {dayKeys.map((day) => (
              <div key={day}>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full bg-emerald-500" />
                  <h3 className="text-sm font-medium text-gray-400">{day}</h3>
                  <span className="text-xs text-gray-600">{groupedEvents[day].length} 个事件</span>
                </div>
                <div className="space-y-2">
                  {groupedEvents[day].map((event) => {
                    const iconKey = icons[event.type] || "activity";
                    const iconInfo = ICON_LABELS[iconKey] || { icon: "●", color: "text-gray-500" };
                    return (
                      <div
                        key={event.id}
                        className="flex items-start gap-3 p-3 bg-gray-900 border border-gray-800 rounded-lg hover:border-gray-700 transition-colors"
                      >
                        <span className={`text-lg ${iconInfo.color} mt-0.5 shrink-0`}>
                          {iconInfo.icon}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-gray-300">{event.description}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-xs text-gray-600">{formatDate(event.ts)}</span>
                            {event.actor && event.actor !== "user" && (
                              <span className="text-xs text-gray-700 bg-gray-800 px-1.5 py-0.5 rounded">
                                {event.actor.startsWith("agent:")
                                  ? "AI"
                                  : event.actor === "scheduler"
                                    ? "定时"
                                    : event.actor}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {hasMore && (
          <div className="flex justify-center py-6">
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="px-6 py-2 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg text-sm transition-colors disabled:opacity-50"
            >
              {loadingMore ? <Loader2 size={14} className="animate-spin inline mr-1" /> : null}
              加载更多
            </button>
          </div>
        )}

        {!hasMore && events.length > 0 && (
          <p className="text-center text-gray-700 text-xs py-6">已经是最早的记录</p>
        )}
      </div>
    </div>
  );
}
