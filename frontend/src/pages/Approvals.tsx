import { useEffect, useState } from "react";
import {
  Check,
  X,
  RefreshCw,
  Clock,
  AlertTriangle,
  FileText,
  Terminal,
  Mail,
  Calendar,
  Send,
} from "lucide-react";
import {
  approveApproval,
  rejectApproval,
  ApiError,
  type EnrichedApproval,
} from "../api/client";
import { useErrorStore } from "../stores/errorStore";
import { useApprovalsQuery, useInvalidateApprovals } from "../hooks/useApprovalsQuery";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Card from "../components/ui/Card";

/** 将 action 名称映射为中文标签和图标 */
const ACTION_META: Record<
  string,
  { label: string; icon: React.ComponentType<{ size?: number; className?: string }> }
> = {
  write_file: { label: "写入文件", icon: FileText },
  apply_patch: { label: "应用补丁", icon: FileText },
  shell_exec: { label: "执行命令", icon: Terminal },
  send_email: { label: "发送邮件", icon: Mail },
  add_calendar_event: { label: "添加日程", icon: Calendar },
  telegram_send: { label: "Telegram 发送", icon: Send },
};

/** 流程类型对应的 Badge 色调 */
const FLOW_TONE: Record<string, "info" | "success" | "warning" | "default" | "danger"> = {
  对话: "info",
  任务: "success",
  定时任务: "warning",
  测试: "default",
  系统: "default",
  未知: "default",
};

export default function ApprovalsPage() {
  const { data: approvals = [], isLoading: loading, error, refetch, isFetching } = useApprovalsQuery();
  const invalidateApprovals = useInvalidateApprovals();
  const [resolving, setResolving] = useState<Set<string>>(new Set());
  const addError = useErrorStore((s) => s.addError);

  useEffect(() => {
    if (error) {
      const msg = error instanceof ApiError ? error.message : "加载审批列表失败";
      addError(msg, "审批");
    }
  }, [error, addError]);

  const handleApprove = async (id: string) => {
    setResolving((prev) => new Set(prev).add(id));
    try {
      await approveApproval(id);
      invalidateApprovals();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "审批操作失败";
      addError(msg, "审批");
    } finally {
      setResolving((prev) => {
        const n = new Set(prev);
        n.delete(id);
        return n;
      });
    }
  };

  const handleReject = async (id: string) => {
    setResolving((prev) => new Set(prev).add(id));
    try {
      await rejectApproval(id, "手动拒绝");
      invalidateApprovals();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "拒绝操作失败";
      addError(msg, "审批");
    } finally {
      setResolving((prev) => {
        const n = new Set(prev);
        n.delete(id);
        return n;
      });
    }
  };

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", { hour12: false });
  };

  const formatTimeAgo = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "刚刚";
    if (mins < 60) return `${mins} 分钟前`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} 小时前`;
    return `${Math.floor(hours / 24)} 天前`;
  };

  const getActionMeta = (action?: string) => {
    return ACTION_META[action || ""] || { label: action || "未知操作", icon: FileText };
  };

  const parseParams = (params?: string) => {
    try {
      if (!params) return null;
      return JSON.parse(params);
    } catch {
      return { raw: params };
    }
  };

  const paramsSummary = (params?: string) => {
    const p = parseParams(params);
    if (!p) return "—";
    if (p.path) return p.path;
    if (p.command) return p.command.length > 80 ? p.command.slice(0, 80) + "..." : p.command;
    return JSON.stringify(p).slice(0, 80);
  };

  const refreshing = loading || isFetching;

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-semibold text-gray-100">审批管理</h2>
            <p className="text-sm text-gray-500 mt-1">管理所有需要人工确认的高风险操作</p>
          </div>
          <div className="flex items-center gap-2">
            {approvals.length > 0 && <Badge tone="warning">{approvals.length} 条待处理</Badge>}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refetch()}
              disabled={refreshing}
            >
              <RefreshCw size={14} className={`inline mr-1 ${refreshing ? "animate-spin" : ""}`} />
              刷新
            </Button>
          </div>
        </div>

        {loading && approvals.length === 0 ? (
          <div className="flex items-center justify-center py-20 text-gray-500">
            <RefreshCw size={20} className="animate-spin mr-2" />
            加载中...
          </div>
        ) : approvals.length === 0 ? (
          <Card className="py-16 text-center">
            <div className="text-gray-500 mb-2">
              <Check size={40} className="mx-auto mb-3 text-emerald-600" />
              <p className="text-lg font-medium text-gray-400">暂无待审批项</p>
              <p className="text-sm text-gray-600 mt-1">所有高风险操作已处理完毕</p>
            </div>
          </Card>
        ) : (
          <div className="space-y-3">
            {approvals.map((item) => (
              <ApprovalCard
                key={item.id}
                item={item}
                resolving={resolving.has(item.id)}
                onApprove={() => handleApprove(item.id)}
                onReject={() => handleReject(item.id)}
                getActionMeta={getActionMeta}
                paramsSummary={paramsSummary}
                formatTime={formatTime}
                formatTimeAgo={formatTimeAgo}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ApprovalCard({
  item,
  resolving,
  onApprove,
  onReject,
  getActionMeta,
  paramsSummary,
  formatTime,
  formatTimeAgo,
}: {
  item: EnrichedApproval;
  resolving: boolean;
  onApprove: () => void;
  onReject: () => void;
  getActionMeta: (action?: string) => {
    label: string;
    icon: React.ComponentType<{ size?: number; className?: string }>;
  };
  paramsSummary: (params?: string) => string;
  formatTime: (iso: string) => string;
  formatTimeAgo: (iso: string) => string;
}) {
  const meta = getActionMeta(item.action);
  const ActionIcon = meta.icon;
  const isExpiringSoon = item.expires_at
    ? new Date(item.expires_at).getTime() - Date.now() < 3600000
    : false;

  return (
    <Card className="p-4 hover:border-gray-700 transition-colors">
      <div className="flex items-start gap-4">
        {/* 操作图标 */}
        <div className="w-10 h-10 rounded-lg bg-gray-800 flex items-center justify-center shrink-0 mt-0.5">
          <ActionIcon size={20} className="text-gray-400" />
        </div>

        {/* 主内容区 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-sm font-medium text-gray-200">{meta.label}</span>
            <Badge tone={FLOW_TONE[item.flow_type] || "default"}>{item.flow_type}</Badge>
            {isExpiringSoon && (
              <Badge tone="danger">
                <AlertTriangle size={10} className="inline mr-0.5" />
                即将过期
              </Badge>
            )}
          </div>

          {/* 流程来源 */}
          <div className="text-xs text-gray-400 mb-1">
            来源：<span className="text-gray-300">{item.flow_label || "—"}</span>
          </div>

          {/* 参数 */}
          <div className="text-xs text-gray-500 font-mono bg-gray-950 rounded px-2 py-1 mt-1 mb-2 truncate max-w-full">
            {paramsSummary(item.params)}
          </div>

          {/* 底部元信息 */}
          <div className="flex items-center gap-4 text-xs text-gray-600 flex-wrap">
            <span className="flex items-center gap-1">
              <Clock size={12} />
              <span title={item.created_at ? formatTime(item.created_at) : "—"}>
                {item.created_at ? formatTimeAgo(item.created_at) : "—"}
              </span>
            </span>
            {item.expires_at && (
              <span className={`${isExpiringSoon ? "text-red-400" : ""}`}>
                过期：{formatTime(item.expires_at)}
              </span>
            )}
            {item.proposed_by && <span>发起：{item.proposed_by}</span>}
            {item.correlation_id && (
              <span className="text-gray-700 truncate max-w-[200px]" title={item.correlation_id}>
                ID: {item.correlation_id}
              </span>
            )}
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-2 shrink-0 self-center">
          <button
            onClick={onApprove}
            disabled={resolving}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/40 disabled:opacity-50 transition-colors"
            title="批准此操作"
          >
            <Check size={14} />
            批准
          </button>
          <button
            onClick={onReject}
            disabled={resolving}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-600/20 text-red-400 hover:bg-red-600/40 disabled:opacity-50 transition-colors"
            title="拒绝此操作"
          >
            <X size={14} />
            拒绝
          </button>
        </div>
      </div>
    </Card>
  );
}
