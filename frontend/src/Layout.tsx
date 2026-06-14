import { useEffect, useState, Suspense } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { useChatStore } from "./stores/chatStore";
import { useErrorStore } from "./stores/errorStore";
import {
  listConversations,
  deleteConversation,
  getSystemHealth,
  isAuthConfigured,
  ApiError,
  type Notification,
} from "./api/client";
import { useQuickChat } from "./hooks/useQuickChat";
import Sidebar from "./components/layout/Sidebar";
import Dialog from "./components/ui/Dialog";
import NotificationBell from "./components/layout/NotificationBell";
import NotificationDetailModal from "./components/notifications/NotificationDetailModal";
import OnboardingWizard from "./components/onboarding/OnboardingWizard";
import { useNotifications } from "./hooks/useNotifications";

export default function Layout() {
  const {
    conversations,
    activeConversationId,
    setConversations,
    setActiveConversation,
    removeConversation,
  } = useChatStore();
  const quickChat = useQuickChat();

  const { toasts, dismissToast } = useNotifications();
  const { errors, dismissError, backendUnavailable, addError } = useErrorStore();
  const [authRequired, setAuthRequired] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(
    () => !localStorage.getItem("onboarding_done")
  );
  const [toastDetail, setToastDetail] = useState<Notification | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    const match = location.pathname.match(/^\/chat\/([^/]+)/);
    const convId = match?.[1] ?? null;
    if (convId && convId !== activeConversationId) {
      setActiveConversation(convId);
    } else if (location.pathname === "/" && activeConversationId) {
      setActiveConversation(null);
    }
  }, [location.pathname, activeConversationId, setActiveConversation]);

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

  const handleNewChat = () => quickChat();

  const handleDeleteChat = (id: string) => {
    const conv = conversations.find((c) => c.id === id);
    setDeleteTarget({ id, title: conv?.title || "新对话" });
  };

  const confirmDeleteChat = async () => {
    if (!deleteTarget) return;
    const { id } = deleteTarget;
    setDeleteTarget(null);
    try {
      await deleteConversation(id);
      removeConversation(id);
      if (activeConversationId === id) {
        navigate("/");
      }
    } catch (e) {
      addError(e instanceof ApiError ? e.message : "删除对话失败", "对话");
    }
  };

  const handleSelectConversation = (id: string) => {
    setActiveConversation(id);
    navigate(`/chat/${id}`);
  };

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      <Sidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
        footer={<NotificationBell />}
      />

      {authRequired && !isAuthConfigured() && (
        <div className="fixed top-0 left-64 right-0 z-50 bg-amber-900/50 border-b border-amber-700/50 px-4 py-2 text-center">
          <span className="text-amber-300 text-sm">
            后端已启用认证，请在 .env 中设置 VITE_AUTH_TOKEN（与 AUTH_TOKEN 保持一致）后重启前端
          </span>
        </div>
      )}

      {backendUnavailable && (
        <div className="fixed top-0 left-64 right-0 z-50 bg-red-900/50 border-b border-red-700/50 px-4 py-2 text-center">
          <span className="text-red-400 text-sm">
            无法连接到后端服务，请确认后端已启动
          </span>
        </div>
      )}

      <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="bg-gray-900 border border-emerald-700/50 rounded-lg p-3 shadow-lg cursor-pointer"
            onClick={() =>
              setToastDetail({
                id: t.id,
                type: t.type,
                title: t.title,
                content: t.content,
                created_at: t.created_at,
              })
            }
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

      <main className="flex-1 flex flex-col min-w-0">
        <Suspense
          fallback={
            <div className="flex-1 flex items-center justify-center text-gray-400 animate-pulse">
              加载中…
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </main>

      <Dialog
        open={!!deleteTarget}
        title="删除对话"
        description={
          deleteTarget
            ? `确定删除对话「${deleteTarget.title}」？此操作不可撤销。`
            : undefined
        }
        confirmLabel="删除"
        variant="danger"
        onConfirm={confirmDeleteChat}
        onCancel={() => setDeleteTarget(null)}
      />

      {showOnboarding && (
        <OnboardingWizard onComplete={() => setShowOnboarding(false)} />
      )}

      <NotificationDetailModal
        notification={toastDetail}
        onClose={() => {
          if (toastDetail) dismissToast(toastDetail.id);
          setToastDetail(null);
        }}
      />
    </div>
  );
}
