import { useEffect, useState } from "react";
import { useChatStore } from "./stores/chatStore";
import { useAppStore } from "./stores/appStore";
import { useErrorStore } from "./stores/errorStore";
import {
  listConversations,
  createConversation,
  deleteConversation,
  getSystemHealth,
  isAuthConfigured,
  ApiError,
} from "./api/client";
import ChatView from "./components/chat/ChatView";
import Sidebar from "./components/layout/Sidebar";
import GoalsPage from "./pages/Goals";
import TimelinePage from "./pages/Timeline";
import DashboardPage from "./pages/Dashboard";
import InboxPage from "./pages/Inbox";
import MemoriesPage from "./pages/Memories";
import { useNotifications } from "./hooks/useNotifications";

export default function App() {
  const {
    conversations,
    activeConversationId,
    setConversations,
    setActiveConversation,
    addConversation,
    removeConversation,
  } = useChatStore();

  const { currentPage, setPage } = useAppStore();
  const { toasts, dismissToast } = useNotifications();
  const { errors, dismissError, backendUnavailable, addError } = useErrorStore();
  const [authRequired, setAuthRequired] = useState(false);

  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async () => {
    try {
      const health = await getSystemHealth();
      setAuthRequired(health.auth_required);
      const convs = await listConversations();
      setConversations(convs);
      useErrorStore.getState().setBackendUnavailable(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        addError(
          "认证失败，请检查 AUTH_TOKEN 与 VITE_AUTH_TOKEN 是否一致",
          "认证"
        );
      } else {
        useErrorStore.getState().setBackendUnavailable(true);
      }
    }
  };

  const handleNewChat = async () => {
    try {
      const conv = await createConversation();
      addConversation(conv);
      setActiveConversation(conv.id);
      setPage("chat");
    } catch (e) {
      addError(e instanceof ApiError ? e.message : "创建对话失败", "对话");
    }
  };

  const handleDeleteChat = async (id: string) => {
    try {
      await deleteConversation(id);
      removeConversation(id);
    } catch (e) {
      addError(e instanceof ApiError ? e.message : "删除对话失败", "对话");
    }
  };

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      <Sidebar
        currentPage={currentPage}
        onNavigate={setPage}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={setActiveConversation}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
      />

      {/* Auth not configured banner */}
      {authRequired && !isAuthConfigured() && (
        <div className="fixed top-0 left-64 right-0 z-50 bg-amber-900/50 border-b border-amber-700/50 px-4 py-2 text-center">
          <span className="text-amber-300 text-sm">
            后端已启用认证，请在 .env 中设置 VITE_AUTH_TOKEN（与 AUTH_TOKEN 保持一致）后重启前端
          </span>
        </div>
      )}

      {/* Backend unavailable banner */}
      {backendUnavailable && (
        <div className="fixed top-0 left-64 right-0 z-50 bg-red-900/50 border-b border-red-700/50 px-4 py-2 text-center">
          <span className="text-red-400 text-sm">
            无法连接到后端服务，请确认后端已启动
          </span>
        </div>
      )}

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
        {errors.map((e) => (
          <div
            key={e.id}
            className="bg-gray-900 border border-red-700/50 rounded-lg p-3 shadow-lg cursor-pointer"
            onClick={() => dismissError(e.id)}
          >
            <div className="text-sm font-medium text-red-400">
              {e.source ? `[${e.source}] ` : ""}错误
            </div>
            <div className="text-xs text-gray-400 mt-1 line-clamp-2">{e.message}</div>
          </div>
        ))}
      </div>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        {currentPage === "chat" &&
          (activeConversationId ? (
            <ChatView conversationId={activeConversationId} />
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="text-6xl mb-4">🧠</div>
                <h2 className="text-2xl font-semibold text-gray-300 mb-2">
                  Personal AI Runtime
                </h2>
                <p className="text-gray-500 mb-6">点击「新对话」开始，或选择一个已有对话</p>
                <button
                  onClick={handleNewChat}
                  className="px-6 py-3 bg-emerald-600 hover:bg-emerald-700 rounded-xl text-white font-medium transition-colors"
                >
                  开始新对话
                </button>
              </div>
            </div>
          ))}
        {currentPage === "goals" && <GoalsPage />}
        {currentPage === "inbox" && <InboxPage />}
        {currentPage === "timeline" && <TimelinePage />}
        {currentPage === "memories" && <MemoriesPage />}
        {currentPage === "dashboard" && <DashboardPage />}
      </main>
    </div>
  );
}
