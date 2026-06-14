import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  listEvents,
  listReviews,
  getReview,
  ApiError,
  type Review,
  type TimelineEvent,
} from "../api/client";
import { useErrorStore } from "../stores/errorStore";
import { useChatStore } from "../stores/chatStore";
import ReviewDetailModal from "../components/reviews/ReviewDetailModal";
import { reviewPeriodLabel, reviewTypeLabel } from "../utils/reviewUtils";

export default function TimelinePage() {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [selectedReview, setSelectedReview] = useState<Review | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const addError = useErrorStore((s) => s.addError);
  const navigate = useNavigate();
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);

  const getConversationId = (event: TimelineEvent): string | null => {
    if (!event.payload) return null;
    try {
      const p = JSON.parse(event.payload);
      return p.conversation_id || p.conv_id || null;
    } catch {
      return null;
    }
  };

  const handleEventClick = (event: TimelineEvent) => {
    const convId = getConversationId(event);
    if (convId) {
      setActiveConversation(convId);
      navigate(`/chat/${convId}`);
    } else if (event.goal_id) {
      navigate(`/goals/${event.goal_id}`);
    }
  };

  const handleReviewClick = async (review: Review) => {
    setSelectedReview(review);
    setReviewLoading(true);
    setReviewError(null);
    try {
      const full = await getReview(review.id);
      setSelectedReview(full);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "加载复盘详情失败";
      setReviewError(msg);
    } finally {
      setReviewLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [eventList, reviewList] = await Promise.all([
        listEvents(30, 50),
        listReviews(5).catch(() => [] as Review[]),
      ]);
      setEvents(eventList);
      setReviews(reviewList);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "加载时间线失败";
      addError(msg, "时间线");
    }
  };

  const groupedByDate = events.reduce((acc, event) => {
    const date = event.timestamp.slice(0, 10);
    if (!acc[date]) acc[date] = [];
    acc[date].push(event);
    return acc;
  }, {} as Record<string, TimelineEvent[]>);

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
            <div className="space-y-3">
              {reviews.slice(0, 3).map((review) => (
                <button
                  key={review.id}
                  type="button"
                  onClick={() => handleReviewClick(review)}
                  className="w-full text-left bg-gray-800 rounded-xl p-4 border border-gray-700 hover:border-emerald-600/40 hover:bg-gray-800/80 transition-colors cursor-pointer"
                >
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="text-xs text-gray-500">
                      {reviewTypeLabel(review.type)}
                      {" · "}
                      {reviewPeriodLabel(review)}
                    </span>
                    <span className="text-xs text-emerald-500 ml-auto">查看全文 →</span>
                  </div>
                  <div className="text-sm text-gray-300 whitespace-pre-wrap line-clamp-6">
                    {(review.content || "").slice(0, 800)}
                  </div>
                </button>
              ))}
            </div>
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
                      onClick={() => handleEventClick(event)}
                      className={`flex items-start gap-3 py-2 px-3 bg-gray-900/50 rounded-lg hover:bg-gray-800/50 transition-colors ${
                        getConversationId(event) || event.goal_id
                          ? "cursor-pointer"
                          : ""
                      }`}
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

      <ReviewDetailModal
        review={selectedReview}
        loading={reviewLoading}
        error={reviewError}
        onClose={() => {
          setSelectedReview(null);
          setReviewError(null);
        }}
      />
    </div>
  );
}
