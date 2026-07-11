import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { type ToolSummaryItem, markNotificationRead, type Notification } from "../api/client";
import { useDashboard } from "../hooks/useDashboard";
import { useNotifications } from "../hooks/useNotifications";
import { toolLabel } from "../utils/toolLabels";
import NotificationDetailModal from "../components/notifications/NotificationDetailModal";
import { notificationPreview } from "../utils/notificationUtils";
import { TrustReportPanel } from "./TrustReport";
import {
  MessageSquare,
  Mail,
  Target,
  Zap,
  AlertCircle,
  Brain,
  Database,
  Shield,
  Download,
  ChevronDown,
  ChevronRight,
  LayoutDashboard,
} from "lucide-react";

function getDateString(): string {
  const d = new Date();
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${weekdays[d.getDay()]}`;
}

function TabBar({
  tab,
  setTab,
}: {
  tab: "overview" | "trust";
  setTab: (next: "overview" | "trust") => void;
}) {
  return (
    <div className="flex gap-1 bg-gray-800 rounded-lg p-1 mb-6 w-fit">
      <button
        type="button"
        onClick={() => setTab("overview")}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors ${
          tab === "overview" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-gray-200"
        }`}
      >
        <LayoutDashboard size={14} />
        概览
      </button>
      <button
        type="button"
        onClick={() => setTab("trust")}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors ${
          tab === "trust" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-gray-200"
        }`}
      >
        <Shield size={14} />
        信任
      </button>
    </div>
  );
}

export default function DashboardPage() {
  const [selectedNotification, setSelectedNotification] = useState<Notification | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "trust" ? "trust" : "overview";
  const setTab = (next: "overview" | "trust") => {
    if (next === "overview") {
      setSearchParams({}, { replace: true });
    } else {
      setSearchParams({ tab: "trust" }, { replace: true });
    }
  };
  const navigate = useNavigate();

  const { cost, tools, memory, health, notifications, dashboard, loading, error, refresh } =
    useDashboard();
  const { liveNotifications } = useNotifications();

  if (tab === "trust") {
    return (
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        <div className="max-w-4xl mx-auto">
          <TabBar tab={tab} setTab={setTab} />
          <TrustReportPanel compact />
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-gray-400 animate-pulse">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="text-gray-500 mb-2">
            <AlertCircle size={32} className="mx-auto mb-2" />
          </div>
          <div className="text-gray-400 mb-4">{error}</div>
          <button
            onClick={refresh}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm transition-colors"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  const totalTokens = (cost?.total_prompt_tokens || 0) + (cost?.total_completion_tokens || 0);
  const successRate =
    cost && cost.total_calls > 0
      ? (((cost.total_calls - cost.failed_calls) / cost.total_calls) * 100).toFixed(1)
      : "100";

  const mergedNotifications = [...liveNotifications, ...notifications]
    .reduce<typeof notifications>((acc, item) => {
      const key = `${item.type}:${item.title}`;
      if (!acc.some((n) => n.id === item.id || `${n.type}:${n.title}` === key)) {
        acc.push(item);
      }
      return acc;
    }, [])
    .slice(0, 6);

  const handleNotificationClick = async (n: Notification) => {
    setSelectedNotification(n);
    if (!n.read) {
      try {
        await markNotificationRead(n.id);
      } catch {
        // still show detail
      }
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-200">AI 概览</h2>
            <p className="text-sm text-gray-500 mt-0.5">{getDateString()}</p>
          </div>
          <button
            onClick={refresh}
            className="px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg transition-colors"
          >
            刷新
          </button>
        </div>

        <TabBar tab={tab} setTab={setTab} />

        {dashboard?.data_sovereignty && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <Database size={16} className="text-emerald-400" />
              <h3 className="text-sm font-medium text-gray-300">我的数据</h3>
              <span className="ml-auto flex items-center gap-1 text-xs text-emerald-600">
                <Shield size={12} />
                全部本地存储
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="text-center py-2">
                <div className="text-2xl font-bold text-indigo-400">
                  {(dashboard.data_sovereignty.total_events || 0).toLocaleString()}
                </div>
                <div className="text-xs text-gray-500 mt-1">个事件</div>
              </div>
              <div className="text-center py-2">
                <div className="text-2xl font-bold text-emerald-400">
                  {(dashboard.data_sovereignty.total_memories || 0).toLocaleString()}
                </div>
                <div className="text-xs text-gray-500 mt-1">条记忆</div>
              </div>
              <div className="text-center py-2">
                <div className="text-2xl font-bold text-amber-400">
                  {(dashboard.data_sovereignty.total_goals || 0).toLocaleString()}
                </div>
                <div className="text-xs text-gray-500 mt-1">个目标</div>
              </div>
              <div className="text-center py-2">
                <div className="text-2xl font-bold text-blue-400">
                  {(dashboard.data_sovereignty.total_conversations || 0).toLocaleString()}
                </div>
                <div className="text-xs text-gray-500 mt-1">个对话</div>
              </div>
            </div>
            <div className="flex items-center gap-4 mb-3 text-xs text-gray-500">
              <span>
                自我陈述:
                <span className="text-indigo-400 ml-1 font-medium">
                  {dashboard.data_sovereignty.memories_self_report || 0}
                </span>
              </span>
              <span>
                AI 提炼:
                <span className="text-amber-400 ml-1 font-medium">
                  {dashboard.data_sovereignty.memories_claim || 0}
                </span>
              </span>
              <span>
                目标进度:
                <span className="text-emerald-400 ml-1 font-medium">
                  {dashboard.data_sovereignty.goals_active || 0} 进行中
                </span>
                <span className="text-gray-600 mx-1">/</span>
                <span className="text-gray-400 font-medium">
                  {dashboard.data_sovereignty.goals_completed || 0} 已完成
                </span>
              </span>
            </div>
            {dashboard.data_sovereignty.last_belief_reflection && (
              <div className="text-xs text-gray-600 mb-3">
                最近一次 AI 反思：
                {new Date(dashboard.data_sovereignty.last_belief_reflection).toLocaleString(
                  "zh-CN",
                )}
              </div>
            )}
            {dashboard.data_sovereignty.export_supported && (
              <button
                onClick={async () => {
                  try {
                    const { exportData } = await import("../api/client");
                    await exportData();
                    alert("数据导出成功");
                  } catch {
                    alert("导出失败，请在设置页面操作");
                  }
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg text-xs transition-colors"
              >
                <Download size={12} />
                导出我的数据
              </button>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-2 mb-6">
          <button
            onClick={() => navigate("/")}
            className="flex items-center gap-2 px-4 py-2.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 rounded-xl border border-emerald-600/30 transition-all text-sm font-medium"
          >
            <MessageSquare size={16} />
            <span>和 AI 对话</span>
          </button>
          <button
            onClick={() => navigate("/inbox")}
            className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl border border-gray-700/50 transition-all text-sm"
          >
            <Mail size={16} className="text-blue-400" />
            <span>查看邮件</span>
          </button>
          <button
            onClick={() => navigate("/goals")}
            className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl border border-gray-700/50 transition-all text-sm"
          >
            <Target size={16} className="text-amber-400" />
            <span>我的目标</span>
          </button>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Brain size={16} className="text-indigo-400" />
            <h3 className="text-sm font-medium text-gray-300">AI 记住了</h3>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center py-2">
              <div className="text-2xl font-bold text-indigo-400">
                {memory?.total_memories || 0}
              </div>
              <div className="text-xs text-gray-500 mt-1">条记忆</div>
            </div>
            <div className="text-center py-2">
              <div className="text-2xl font-bold text-emerald-400">{memory?.recent_7d || 0}</div>
              <div className="text-xs text-gray-500 mt-1">近 7 天新增</div>
            </div>
            <div className="text-center py-2">
              <div className="text-2xl font-bold text-amber-400">
                {memory ? Object.keys(memory.categories).length : 0}
              </div>
              <div className="text-xs text-gray-500 mt-1">个分类</div>
            </div>
          </div>
          {memory && Object.keys(memory.categories).length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-800">
              <div className="flex flex-wrap gap-2">
                {Object.entries(memory.categories).map(([cat, count]) => (
                  <button
                    key={cat}
                    onClick={() => navigate("/memories")}
                    className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs text-gray-400 transition-colors"
                  >
                    {cat}: {count}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={15} className="text-amber-400" />
            <h3 className="text-sm font-medium text-gray-300">AI 给你的提醒</h3>
          </div>
          {mergedNotifications.length > 0 ? (
            <div className="space-y-2">
              {mergedNotifications.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => void handleNotificationClick(n)}
                  className={`w-full text-left p-3 bg-gray-800/50 rounded-lg hover:bg-gray-800 transition-colors ${
                    n.read ? "opacity-60" : ""
                  }`}
                >
                  <div className={`text-sm ${n.read ? "text-gray-400" : "text-emerald-400"}`}>
                    {n.title}
                  </div>
                  <div className="text-xs text-gray-400 mt-1 line-clamp-2">
                    {notificationPreview(n.content)}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-gray-600 text-sm text-center py-4">暂无提醒</p>
          )}
        </div>

        <div className="border-t border-gray-800 pt-4">
          <button
            onClick={() => setShowDiagnostics(!showDiagnostics)}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-500 hover:text-gray-400 transition-colors"
          >
            {showDiagnostics ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span>系统诊断（开发者用）</span>
          </button>

          {showDiagnostics && (
            <div className="mt-3 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">LLM 成功率</div>
                  <div
                    className="text-lg font-bold"
                    style={{ color: Number(successRate) >= 95 ? "#10b981" : "#f59e0b" }}
                  >
                    {successRate}%
                  </div>
                </div>
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">任务队列</div>
                  <div className="text-lg font-bold text-gray-300">
                    {health?.task_queue_length ?? 0}
                  </div>
                </div>
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">工具失败率</div>
                  <div
                    className="text-lg font-bold"
                    style={{
                      color: (health?.tool_failure_rate_24h || 0) < 0.05 ? "#10b981" : "#ef4444",
                    }}
                  >
                    {((health?.tool_failure_rate_24h || 0) * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="text-xs text-gray-500 mb-3">Token 与成本 (7天)</div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">总 Token</span>
                    <span className="text-gray-300 font-mono">{totalTokens.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">预估费用</span>
                    <span className="text-gray-300 font-mono">
                      ${(cost?.total_cost || 0).toFixed(4)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">调用次数</span>
                    <span className="text-gray-300 font-mono">{cost?.total_calls || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">平均延迟</span>
                    <span className="text-gray-300 font-mono">
                      {(cost?.avg_latency_ms || 0).toFixed(0)}ms
                    </span>
                  </div>
                </div>
              </div>

              {tools.length > 0 && (
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                  <div className="text-xs text-gray-500 mb-2">工具调用 (7天)</div>
                  <div className="space-y-1">
                    {tools.map((t: ToolSummaryItem) => {
                      const rate =
                        t.total_calls > 0
                          ? (((t.total_calls - t.failed_calls) / t.total_calls) * 100).toFixed(0)
                          : "0";
                      const color =
                        Number(rate) >= 95 ? "#10b981" : Number(rate) >= 80 ? "#f59e0b" : "#ef4444";
                      return (
                        <div
                          key={t.tool_name}
                          className="flex items-center justify-between py-1.5 text-xs"
                        >
                          <span className="text-gray-400">{toolLabel(t.tool_name)}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-gray-600">{t.total_calls} 次</span>
                            <span style={{ color }}>{rate}%</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <NotificationDetailModal
        notification={selectedNotification}
        onClose={() => setSelectedNotification(null)}
      />
    </div>
  );
}
