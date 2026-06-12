import { type Page } from "../../stores/appStore";

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: "chat", label: "对话", icon: "💬" },
  { id: "goals", label: "目标", icon: "🎯" },
  { id: "inbox", label: "收件箱", icon: "📧" },
  { id: "timeline", label: "时间线", icon: "📅" },
  { id: "memories", label: "记忆", icon: "🧩" },
  { id: "dashboard", label: "仪表盘", icon: "📊" },
];

interface SidebarProps {
  currentPage: Page;
  onNavigate: (page: Page) => void;
  conversations: Array<{ id: string; title: string }>;
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
}

export default function Sidebar({
  currentPage,
  onNavigate,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteChat,
}: SidebarProps) {
  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-lg font-bold text-emerald-400">Personal AI Runtime</h1>
        <p className="text-xs text-gray-500 mt-1">你的第二大脑</p>
      </div>

      <nav className="px-2 py-2 border-b border-gray-800">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
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
            onClick={onNewChat}
            className="mx-3 mt-3 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-medium transition-colors"
          >
            + 新对话
          </button>

          <div className="flex-1 overflow-y-auto mt-3 px-2">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => onSelectConversation(conv.id)}
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
                    onDeleteChat(conv.id);
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
  );
}
