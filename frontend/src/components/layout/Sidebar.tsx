import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  MessageSquare,
  Target,
  Mail,
  Brain,
  BarChart3,
  Settings,
  ShieldCheck,
  Trash2,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  Clock,
  BookOpen,
} from "lucide-react";
import { useApprovalsQuery } from "../../hooks/useApprovalsQuery";
import { useInboxQuery } from "../../hooks/useInboxQuery";

const PRIMARY_NAV = [{ path: "/", label: "对话", icon: MessageSquare, matchChat: true }];

const DATA_NAV = [
  { path: "/dashboard", label: "概览", icon: BarChart3, badgeKey: null },
  { path: "/goals", label: "目标", icon: Target, badgeKey: null },
  { path: "/inbox", label: "收件箱", icon: Mail, badgeKey: "inbox" as const },
  { path: "/approvals", label: "审批", icon: ShieldCheck, badgeKey: "approvals" as const },
  { path: "/memories", label: "记忆", icon: Brain, badgeKey: null },
  { path: "/timeline", label: "时间线", icon: Clock, badgeKey: null },
  { path: "/knowledge", label: "知识库", icon: BookOpen, badgeKey: null },
];

const SYSTEM_NAV = [{ path: "/settings", label: "设置", icon: Settings }];

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

function isDataRoute(pathname: string) {
  return DATA_NAV.some((item) => pathname.startsWith(item.path));
}

function NavBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="ml-auto text-[10px] min-w-[1.25rem] h-5 px-1.5 rounded-full bg-amber-600/30 text-amber-300 flex items-center justify-center font-medium">
      {count > 99 ? "99+" : count}
    </span>
  );
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
  const [dataExpanded, setDataExpanded] = useState(isDataRoute(location.pathname));
  const { data: approvals = [] } = useApprovalsQuery();
  const { data: inbox } = useInboxQuery();
  const approvalCount = approvals.length;
  const inboxCount = inbox?.emails?.length ?? 0;

  const badgeFor = (key: "inbox" | "approvals" | null) => {
    if (key === "approvals") return approvalCount;
    if (key === "inbox") return inboxCount;
    return 0;
  };

  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-lg font-bold text-emerald-400">Personal AI Runtime</h1>
        <p className="text-xs text-gray-500 mt-1">你的第二大脑</p>
      </div>

      <nav className="px-2 py-2 border-b border-gray-800">
        {PRIMARY_NAV.map((item) => {
          const Icon = item.icon;
          const active = isChatRoute(location.pathname);
          return (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm mb-1 transition-colors ${
                active ? "bg-emerald-600/20 text-emerald-400" : "text-gray-400 hover:bg-gray-800/50"
              }`}
            >
              <Icon size={18} className="shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}

        {/* Always-visible decision shortcuts when something needs attention */}
        {(approvalCount > 0 || inboxCount > 0) && (
          <div className="mt-1 space-y-0.5">
            {approvalCount > 0 && (
              <NavLink
                to="/approvals"
                className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-amber-300/90 hover:bg-amber-900/20 transition-colors"
              >
                <ShieldCheck size={14} className="shrink-0" />
                <span>待审批</span>
                <NavBadge count={approvalCount} />
              </NavLink>
            )}
            {inboxCount > 0 && (
              <NavLink
                to="/inbox"
                className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-blue-300/90 hover:bg-blue-900/20 transition-colors"
              >
                <Mail size={14} className="shrink-0" />
                <span>待处理邮件</span>
                <NavBadge count={inboxCount} />
              </NavLink>
            )}
          </div>
        )}
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
                  <span className="truncate text-sm block">{conv.title || "新对话"}</span>
                  {conv.summary && (
                    <span className="truncate text-xs text-gray-600 block">{conv.summary}</span>
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

      {!onChatPage && (
        <div className="px-2 py-2 flex-1 overflow-y-auto">
          <button
            onClick={() => setDataExpanded(!dataExpanded)}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-gray-500 hover:text-gray-400 transition-colors uppercase tracking-wide"
          >
            {dataExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <FolderOpen size={14} />
            <span>我的数据</span>
          </button>
          {dataExpanded && (
            <div className="mt-1">
              {DATA_NAV.map((item) => {
                const Icon = item.icon;
                const count = badgeFor(item.badgeKey);
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    className={({ isActive }) =>
                      `w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm mb-1 transition-colors ${
                        isActive
                          ? "bg-emerald-600/20 text-emerald-400"
                          : "text-gray-400 hover:bg-gray-800/50"
                      }`
                    }
                  >
                    <Icon size={18} className="shrink-0" />
                    <span>{item.label}</span>
                    <NavBadge count={count} />
                  </NavLink>
                );
              })}
            </div>
          )}
        </div>
      )}

      <div className="border-t border-gray-800 px-2 py-2 mt-auto">
        {SYSTEM_NAV.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-emerald-600/20 text-emerald-400"
                    : "text-gray-400 hover:bg-gray-800/50"
                }`
              }
            >
              <Icon size={18} className="shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>

      {footer}
    </aside>
  );
}
