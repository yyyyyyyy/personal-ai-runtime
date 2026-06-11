import { useState, useEffect } from "react";

interface Event {
  id: string;
  type: string;
  summary: string;
  timestamp: string;
  goal_id: string | null;
  payload: string | null;
}

interface Review {
  id: string;
  type: string;
  period_start: string;
  period_end: string;
  content: string;
  created_at: string;
}

export default function TimelinePage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [goals, setGoals] = useState<any[]>([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [eventsRes, reviewsRes, goalsRes] = await Promise.all([
        fetch("/api/events/?days=30&limit=50"),
        fetch("/api/reviews/?limit=10"),
        fetch("/api/goals/?limit=50"),
      ]);
      if (eventsRes.ok) setEvents(await eventsRes.json());
      if (reviewsRes.ok) setReviews(await reviewsRes.json());
      if (goalsRes.ok) setGoals(await goalsRes.json());
    } catch {
      // Backend may not be running
    }
  };

  const groupedByDate = events.reduce((acc, event) => {
    const date = event.timestamp.slice(0, 10);
    if (!acc[date]) acc[date] = [];
    acc[date].push(event);
    return acc;
  }, {} as Record<string, Event[]>);

  const sortedDates = Object.keys(groupedByDate).sort().reverse();

  const typeLabels: Record<string, string> = {
    conversation: "对话",
    tool_call: "工具调用",
    goal_created: "创建目标",
    goal_status_changed: "目标状态变更",
    action_created: "添加行动",
    action_status_changed: "行动状态变更",
    test: "测试事件",
  };

  const typeIcons: Record<string, string> = {
    conversation: "💬",
    tool_call: "🔧",
    goal_created: "🎯",
    goal_status_changed: "🏁",
    action_created: "✅",
    action_status_changed: "🔄",
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold mb-6">人生时间线</h2>

        {reviews.length > 0 && (
          <div className="mb-8">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">最近复盘</h3>
            {reviews.slice(0, 1).map((review) => (
              <div key={review.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                <div className="text-xs text-gray-500 mb-2">
                  {review.type === "daily" ? "每日复盘" : review.type === "weekly" ? "每周复盘" : "每月复盘"}
                  {" · "}
                  {review.period_start} ~ {review.period_end}
                </div>
                <div className="text-sm text-gray-300 whitespace-pre-wrap">{review.content.slice(0, 500)}</div>
              </div>
            ))}
          </div>
        )}

        {sortedDates.length === 0 ? (
          <div className="text-gray-500 text-center py-12">
            暂无事件记录。开始使用 Personal AI Runtime 后，这里将显示你的活动时间线。
          </div>
        ) : (
          <div className="relative pl-8 border-l-2 border-gray-800">
            {sortedDates.map((date) => (
              <div key={date} className="mb-8">
                <div className="absolute -left-3 w-5 h-5 bg-emerald-600 rounded-full border-4 border-gray-950" />
                <div className="text-sm font-medium text-emerald-400 mb-3 ml-6">
                  {new Date(date).toLocaleDateString("zh-CN", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                    weekday: "long",
                  })}
                </div>
                <div className="space-y-2 ml-6">
                  {groupedByDate[date].map((event) => (
                    <div
                      key={event.id}
                      className="flex items-start gap-3 py-2 px-3 bg-gray-900/50 rounded-lg hover:bg-gray-800/50 transition-colors"
                    >
                      <span className="text-sm mt-0.5">{typeIcons[event.type] || "📌"}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-300">{event.summary}</div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-gray-600">
                            {new Date(event.timestamp).toLocaleTimeString("zh-CN", {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                          <span className="text-xs text-gray-700">
                            {typeLabels[event.type] || event.type}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
