import { useEffect } from "react";
import { useChatStore } from "./stores/chatStore";
import { useAppStore, type Page } from "./stores/appStore";
import {
  listConversations,
  createConversation,
  deleteConversation,
  fetchSystemInfo,
} from "./api/client";
import ChatView from "./components/chat/ChatView";
import GoalsPage from "./pages/Goals";
import TimelinePage from "./pages/Timeline";
import DashboardPage from "./pages/Dashboard";
import InboxPage from "./pages/Inbox";
import MemoriesPage from "./pages/Memories";
import TrajectoriesPage from "./pages/Trajectories";
import { useNotifications } from "./hooks/useNotifications";

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: "chat", label: "对话", icon: "💬" },
  { id: "goals", label: "目标", icon: "🎯" },
  { id: "inbox", label: "收件箱", icon: "📧" },
  { id: "timeline", label: "时间线", icon: "📅" },
  { id: "memories", label: "记忆", icon: "🧩" },
  { id: "trajectories", label: "轨迹", icon: "〰️" },
  { id: "dashboard", label: "仪表盘", icon: "📊" },
];

export default function App() {
  const {
    conversations,
    activeConversationId,
    setConversations,
    setActiveConversation,
    addConversation,
    removeConversation,
  } = useChatStore();

  const {
    currentPage,
    setPage,
    experimentalTrajectoryEnabled,
    setExperimentalTrajectoryEnabled,
  } = useAppStore();
  const { toasts, dismissToast } = useNotifications();

  const visibleNavItems = NAV_ITEMS.filter(
    (item) => item.id !== "trajectories" || experimentalTrajectoryEnabled
  );

  useEffect(() => {
    loadConversations();
    fetchSystemInfo()
      .then((info) => setExperimentalTrajectoryEnabled(info.experimental_trajectory_enabled))
      .catch(() => {
        // Backend may not be running
      });
  }, [setExperimentalTrajectoryEnabled]);

  useEffect(() => {
    if (!experimentalTrajectoryEnabled && currentPage === "trajectories") {
      setPage("chat");
    }
  }, [experimentalTrajectoryEnabled, currentPage, setPage]);

  const loadConversations = async () => {
    try {
      const convs = await listConversations();
      setConversations(convs);
    } catch {
      // Backend may not be running
    }
  };

  const handleNewChat = async () => {
    try {
      const conv = await createConversation();
      addConversation(conv);
      setActiveConversation(conv.id);
      setPage("chat");
    } catch {
      // backend may not be running
    }
  };

  const handleDeleteChat = async (id: string) => {
    try {
      await deleteConversation(id);
      removeConversation(id);
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">
        <div className="p-4 border-b border-gray-800">
          <h1 className="text-lg font-bold text-emerald-400">Personal AI Runtime</h1>
          <p className="text-xs text-gray-500 mt-1">你的第二大脑</p>
        </div>

        {/* Navigation */}
        <nav className="px-2 py-2 border-b border-gray-800">
          {visibleNavItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setPage(item.id)}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm mb-1 transition-colors ${
                currentPage === item.id
                  ? "bg-emerald-600/20 text-emerald-400"
                  : "text-gray-400 hover:bg-gray-800/50"
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        {currentPage === "chat" && (
          <>
            <button
              onClick={handleNewChat}
              className="mx-3 mt-3 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-medium transition-colors"
            >
              + 新对话
            </button>

            <div className="flex-1 overflow-y-auto mt-3 px-2">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => setActiveConversation(conv.id)}
                  className={`group flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer mb-1 transition-colors ${
                    activeConversationId === conv.id
                      ? "bg-gray-800 text-white"
                      : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
                  }`}
                >
                  <span className="truncate text-sm">{conv.title || "New Chat"}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteChat(conv.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all ml-2 shrink-0"
                    title="删除对话"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                    </svg>
                  </button>
                </div>
              ))}
              {conversations.length === 0 && (
                <p className="text-gray-600 text-sm text-center mt-8">暂无对话</p>
              )}
            </div>
          </>
        )}

        <div className="p-3 border-t border-gray-800 text-xs text-gray-600 text-center mt-auto">
          v0.9.0
        </div>
      </aside>

      {/* Toast notifications */}
      <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="bg-gray-900 border border-emerald-700/50 rounded-lg p-3 shadow-lg cursor-pointer"
            onClick={() => dismissToast(t.id)}
          >
            <div className="text-sm font-medium text-emerald-400">{t.title}</div>
            <div className="text-xs text-gray-400 mt-1 line-clamp-2">{t.content}</div>
          </div>
        ))}
      </div>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        {currentPage === "chat" && (
          activeConversationId ? (
            <ChatView conversationId={activeConversationId} />
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="text-6xl mb-4">🧠</div>
                <h2 className="text-2xl font-semibold text-gray-300 mb-2">
                  Personal AI Runtime
                </h2>
                <p className="text-gray-500 mb-6">
                  点击「新对话」开始，或选择一个已有对话
                </p>
                <button
                  onClick={handleNewChat}
                  className="px-6 py-3 bg-emerald-600 hover:bg-emerald-700 rounded-xl text-white font-medium transition-colors"
                >
                  开始新对话
                </button>
              </div>
            </div>
          )
        )}
        {currentPage === "goals" && <GoalsPage />}
        {currentPage === "inbox" && <InboxPage />}
        {currentPage === "timeline" && <TimelinePage />}
        {currentPage === "memories" && <MemoriesPage />}
        {experimentalTrajectoryEnabled && currentPage === "trajectories" && (
          <TrajectoriesPage />
        )}
        {currentPage === "dashboard" && <DashboardPage />}
      </main>
    </div>
  );
}
