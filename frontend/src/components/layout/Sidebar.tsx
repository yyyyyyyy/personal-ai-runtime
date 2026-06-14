import { NavLink, useLocation } from "react-router-dom";
import {
  MessageSquare,
  Target,
  Mail,
  Brain,
  BookOpen,
  BarChart3,
  History,
  Settings,
  Trash2,
} from "lucide-react";

const NAV_ITEMS: {
  path: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  matchChat?: boolean;
}[] = [
  { path: "/", label: "对话", icon: MessageSquare, matchChat: true },
  { path: "/goals", label: "目标", icon: Target },
  { path: "/inbox", label: "收件箱", icon: Mail },
  { path: "/memories", label: "记忆", icon: Brain },
  { path: "/knowledge", label: "知识库", icon: BookOpen },
  { path: "/dashboard", label: "仪表盘", icon: BarChart3 },
  { path: "/timeline", label: "时间线", icon: History },
  { path: "/settings", label: "设置", icon: Settings },
];

interface SidebarProps {
  conversations: Array<{ id: string; title: string; summary?: string | null }>;
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
  footer?: React.ReactNode;
}

function isChatRoute(pathname: string) {
  return pathname === "/" || pathname.startsWith("/chat/");
}

export default function Sidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteChat,
  footer,
}: SidebarProps) {
  const location = useLocation();
  const onChatPage = isChatRoute(location.pathname);

  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-lg font-bold text-emerald-400">Personal AI Runtime</h1>
        <p className="text-xs text-gray-500 mt-1">你的第二大脑</p>
      </div>

      <nav className="px-2 py-2 border-b border-gray-800">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) => {
                const active = item.matchChat
                  ? isChatRoute(location.pathname)
                  : isActive;
                return `w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm mb-1 transition-colors ${
                  active
                    ? "bg-emerald-600/20 text-emerald-400"
                    : "text-gray-400 hover:bg-gray-800/50"
                }`;
              }}
            >
              <Icon size={18} className="shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      {onChatPage && (
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
                <div className="min-w-0 flex-1">
                  <span className="truncate text-sm block">
                    {conv.title || "新对话"}
                  </span>
                  {conv.summary && (
                    <span className="truncate text-xs text-gray-600 block">
                      {conv.summary}
                    </span>
                  )}
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteChat(conv.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all ml-2 shrink-0"
                  title="删除对话"
                  aria-label="删除对话"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {conversations.length === 0 && (
              <p className="text-gray-600 text-sm text-center mt-8">暂无对话</p>
            )}
          </div>
        </>
      )}

      {footer}

      <div className="p-3 border-t border-gray-800 text-xs text-gray-600 text-center mt-auto">
        v0.9.0
      </div>
    </aside>
  );
}
