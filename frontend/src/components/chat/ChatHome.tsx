import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useChatStore } from "../../stores/chatStore";
import {
  createConversation,
  listReviews,
  listMemoriesGrouped,
  listGoals,
  listInboxEmails,
  triggerMorningBrief,
  ApiError,
  type Review,
  type Conversation,
} from "../../api/client";
import { useErrorStore } from "../../stores/errorStore";
import { timeAgo, isStagnant } from "../../utils/timeUtils";

const BRIEF_CACHE_KEY = "morning_brief_cache";

export default function ChatHome() {
  const navigate = useNavigate();
  const conversations = useChatStore((s) => s.conversations);
  const addConversation = useChatStore((s) => s.addConversation);
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const addError = useErrorStore((s) => s.addError);

  const [brief, setBrief] = useState<string | null>(null);
  const [loadingBrief, setLoadingBrief] = useState(false);
  const [weeklyReview, setWeeklyReview] = useState<Review | null>(null);
  const [memoryCount, setMemoryCount] = useState(0);
  const [stagnantGoalCount, setStagnantGoalCount] = useState(0);
  const [unreadInbox, setUnreadInbox] = useState(0);
  const [loadingInsights, setLoadingInsights] = useState(true);

  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 12) return "早上好";
    if (h < 18) return "下午好";
    return "晚上好";
  })();

  const today = new Date().toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  useEffect(() => {
    loadBrief();
    loadInsights();
  }, []);

  const loadBrief = () => {
    const cached = localStorage.getItem(BRIEF_CACHE_KEY);
    if (cached) {
      try {
        const { content, date } = JSON.parse(cached);
        if (date === new Date().toISOString().slice(0, 10)) {
          setBrief(content);
          return;
        }
      } catch {
        // ignore
      }
    }
    loadBriefFromReviews();
  };

  const loadBriefFromReviews = async () => {
    try {
      const reviews = await listReviews(5);
      const morning = reviews.find((r) => r.type === "morning");
      const weekly = reviews.find((r) => r.type === "weekly");
      if (morning?.content) setBrief(morning.content.slice(0, 300));
      if (weekly) setWeeklyReview(weekly);
    } catch {
      // optional
    }
  };

  const loadInsights = async () => {
    try {
      const [memories, goals, inbox] = await Promise.all([
        listMemoriesGrouped().catch(() => ({ memories: [] })),
        listGoals().catch(() => []),
        listInboxEmails().catch(() => []),
      ]);
      setMemoryCount(memories.memories?.length ?? 0);
      setStagnantGoalCount(goals.filter((g) => g.status === "active" && isStagnant(g.last_activity_at)).length);
      setUnreadInbox(inbox.filter((e) => !e.notified).length);
    } catch {
      // optional
    } finally {
      setLoadingInsights(false);
    }
  };

  const handleRefreshBrief = async () => {
    setLoadingBrief(true);
    try {
      const res = await triggerMorningBrief();
      const content =
        typeof res.result === "string"
          ? res.result
          : (res.result as { content?: string })?.content || "简报已生成";
      setBrief(content.slice(0, 300));
      localStorage.setItem(
        BRIEF_CACHE_KEY,
        JSON.stringify({ content, date: new Date().toISOString().slice(0, 10) })
      );
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "生成简报失败";
      addError(msg, "简报");
    } finally {
      setLoadingBrief(false);
    }
  };

  const handleNewChat = async () => {
    try {
      const conv = await createConversation();
      addConversation(conv);
      setActiveConversation(conv.id);
      navigate(`/chat/${conv.id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "创建对话失败";
      addError(msg, "对话");
    }
  };

  const handleContinueConversation = (conv: Conversation) => {
    setActiveConversation(conv.id);
    navigate(`/chat/${conv.id}`);
  };

  const lastConversation = conversations
    .filter((c) => c.updated_at)
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())[0];

  const hasAnyContent = brief || weeklyReview || lastConversation || memoryCount > 0;

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center pt-6">
          <div className="text-5xl mb-4">🧠</div>
          <h2 className="text-2xl font-semibold text-gray-200">
            {greeting}，欢迎回来
          </h2>
          <p className="text-gray-500 mt-2">{today}</p>
        </div>

        {/* Insight chips */}
        {!loadingInsights && (
          <div className="flex flex-wrap justify-center gap-2">
            {memoryCount > 0 && (
              <span className="text-xs px-3 py-1 bg-emerald-900/30 border border-emerald-700/30 rounded-full text-emerald-400">
                🧠 {memoryCount} 条记忆
              </span>
            )}
            {stagnantGoalCount > 0 && (
              <span className="text-xs px-3 py-1 bg-amber-900/30 border border-amber-700/30 rounded-full text-amber-400">
                ⚠️ {stagnantGoalCount} 个停滞目标
              </span>
            )}
            {unreadInbox > 0 && (
              <span className="text-xs px-3 py-1 bg-blue-900/30 border border-blue-700/30 rounded-full text-blue-400">
                📬 {unreadInbox} 封未读邮件
              </span>
            )}
          </div>
        )}

        {/* Today's brief */}
        {brief && (
          <div className="bg-gray-900 border border-emerald-800/30 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-emerald-400">📋 今日简报</h3>
              <button
                onClick={handleRefreshBrief}
                disabled={loadingBrief}
                className="text-xs text-gray-500 hover:text-gray-300"
              >
                {loadingBrief ? "生成中…" : "刷新"}
              </button>
            </div>
            <p className="text-sm text-gray-400 whitespace-pre-wrap line-clamp-4">
              {brief}
            </p>
            {brief.length >= 300 && (
              <button
                onClick={handleRefreshBrief}
                className="text-xs text-emerald-500 hover:text-emerald-400 mt-1"
              >
                查看完整简报
              </button>
            )}
          </div>
        )}

        {/* Weekly review */}
        {weeklyReview && weeklyReview.content && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <h3 className="text-sm font-medium text-gray-400 mb-2">📊 本周回顾</h3>
            <p className="text-sm text-gray-400 whitespace-pre-wrap line-clamp-3">
              {weeklyReview.content.slice(0, 200)}
            </p>
          </div>
        )}

        {/* Continue last conversation */}
        {lastConversation && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-emerald-600/30 transition-colors cursor-pointer"
            onClick={() => handleContinueConversation(lastConversation)}
          >
            <h3 className="text-sm font-medium text-gray-400 mb-2">💬 继续上次话题</h3>
            <p className="text-sm text-gray-200">{lastConversation.title || "新对话"}</p>
            {lastConversation.summary && (
              <p className="text-xs text-gray-500 mt-1 line-clamp-1">{lastConversation.summary}</p>
            )}
            <p className="text-xs text-gray-600 mt-2">{timeAgo(lastConversation.updated_at)}</p>
          </div>
        )}

        {/* Stagnant goals alert */}
        {stagnantGoalCount > 0 && (
          <div className="bg-amber-900/20 border border-amber-700/30 rounded-xl p-4">
            <h3 className="text-sm font-medium text-amber-400 mb-2">⚠️ 目标需要关注</h3>
            <p className="text-xs text-amber-400/60 mb-3">
              你有 {stagnantGoalCount} 个目标停滞超过 3 天，要聊聊如何推进吗？
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => navigate("/goals")}
                className="text-xs px-3 py-1.5 bg-amber-700/30 hover:bg-amber-700/50 text-amber-300 rounded-lg transition-colors"
              >
                查看目标
              </button>
              {stagnantGoalCount === 1 && lastConversation && (
                <button
                  onClick={() => handleContinueConversation(lastConversation)}
                  className="text-xs px-3 py-1.5 bg-gray-700/50 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors"
                >
                  聊聊目标
                </button>
              )}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!hasAnyContent && (
          <div className="text-center py-4">
            <p className="text-gray-500 text-sm">
              这是你的第二大脑。开始一段对话，我会记住对你重要的每一件事。
            </p>
          </div>
        )}

        {/* Quick actions */}
        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => navigate("/inbox")}
            className="p-4 bg-gray-900 border border-gray-800 rounded-xl hover:border-emerald-600/50 transition-colors text-sm text-gray-300 text-left"
          >
            <div className="text-lg mb-1">📬</div>
            <div className="font-medium">收件箱</div>
            <div className="text-xs text-gray-500 mt-0.5">
              {unreadInbox > 0 ? `${unreadInbox} 封未读` : "查看邮件"}
            </div>
          </button>
          <button
            onClick={() => navigate("/goals")}
            className="p-4 bg-gray-900 border border-gray-800 rounded-xl hover:border-emerald-600/50 transition-colors text-sm text-gray-300 text-left"
          >
            <div className="text-lg mb-1">🎯</div>
            <div className="font-medium">目标</div>
            <div className="text-xs text-gray-500 mt-0.5">
              {stagnantGoalCount > 0 ? `${stagnantGoalCount} 个需关注` : "管理目标"}
            </div>
          </button>
          <button
            onClick={() => navigate("/memories")}
            className="p-4 bg-gray-900 border border-gray-800 rounded-xl hover:border-emerald-600/50 transition-colors text-sm text-gray-300 text-left"
          >
            <div className="text-lg mb-1">🧠</div>
            <div className="font-medium">记忆</div>
            <div className="text-xs text-gray-500 mt-0.5">
              {memoryCount > 0 ? `${memoryCount} 条记忆` : "AI 记忆"}
            </div>
          </button>
          <button
            onClick={() => navigate("/settings")}
            className="p-4 bg-gray-900 border border-gray-800 rounded-xl hover:border-emerald-600/50 transition-colors text-sm text-gray-300 text-left"
          >
            <div className="text-lg mb-1">⚙️</div>
            <div className="font-medium">设置</div>
            <div className="text-xs text-gray-500 mt-0.5">系统状态</div>
          </button>
        </div>

        {/* Start new chat */}
        <div className="text-center pb-8">
          <button
            onClick={handleNewChat}
            className="px-6 py-3 bg-emerald-600 hover:bg-emerald-700 rounded-xl text-white font-medium transition-colors"
          >
            开始新对话
          </button>
        </div>
      </div>
    </div>
  );
}
