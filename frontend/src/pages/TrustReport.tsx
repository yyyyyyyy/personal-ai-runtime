import { useState } from "react";
import { Navigate } from "react-router-dom";
import {
  Shield,
  Database,
  Cpu,
  Activity,
  AlertTriangle,
  AlertCircle,
  Loader2,
  RefreshCw,
  Brain,
  MessageSquare,
  Target,
  FileText,
  Download,
} from "lucide-react";
import { retryMemoryIndexRepair } from "../api/telemetry";
import { useTrustReportQuery, useInvalidateTrustReport } from "../hooks/useTrustReportQuery";

const FLOW_LABELS: Record<string, { label: string; color: string }> = {
  对话: { label: "对话", color: "text-blue-400" },
  任务: { label: "任务", color: "text-purple-400" },
  定时任务: { label: "定时任务", color: "text-amber-400" },
  测试: { label: "测试", color: "text-gray-400" },
  系统: { label: "系统", color: "text-emerald-400" },
};

/** Trust report content — embedded as a Dashboard tab; also used by tests. */
export function TrustReportPanel({ compact = false }: { compact?: boolean }) {
  const { data, isLoading: loading, error: queryError, refetch } = useTrustReportQuery();
  const invalidate = useInvalidateTrustReport();
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const error =
    actionError ??
    (queryError instanceof Error ? queryError.message : queryError ? String(queryError) : null);

  const handleRetryRepair = async (repairId: number) => {
    setRetryingId(repairId);
    setActionError(null);
    try {
      await retryMemoryIndexRepair(repairId);
      invalidate();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "重试索引修复失败");
    } finally {
      setRetryingId(null);
    }
  };

  if (loading) {
    return (
      <div className={`flex items-center justify-center ${compact ? "py-16" : "h-full"}`}>
        <div className="flex flex-col items-center gap-3 text-gray-400">
          <Loader2 size={32} className="animate-spin" />
          <p className="text-sm">正在生成信任报告…</p>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className={`flex items-center justify-center ${compact ? "py-16" : "h-full"}`}>
        <div className="flex flex-col items-center gap-3 text-gray-400">
          <AlertCircle size={32} className="text-red-400" />
          <p className="text-sm">{error}</p>
          <button
            onClick={() => {
              setActionError(null);
              void refetch();
            }}
            className="flex items-center gap-2 px-4 py-2 mt-2 text-sm bg-emerald-600/20 text-emerald-400 rounded-lg hover:bg-emerald-600/30 transition-colors"
          >
            <RefreshCw size={14} />
            重试
          </button>
        </div>
      </div>
    );
  }

  const sov = data?.dashboard?.data_sovereignty;
  const pendingCount = data?.approvals?.length ?? 0;
  const failedRepairs =
    data?.memoryIndexRepairs?.items.filter((r) => r.status === "failed_permanent") ?? [];
  const failedRepairCount = data?.memoryIndexRepairs?.failed_permanent ?? failedRepairs.length;
  const tc = data?.cost?.total_calls ?? 0;
  const tcost = data?.cost?.total_cost ?? 0;
  const alat = data?.cost?.avg_latency_ms ?? 0;
  const fc = data?.cost?.failed_calls ?? 0;
  const rate = tc > 0 ? Math.round(((tc - fc) / tc) * 100) : 100;

  return (
    <div className={compact ? "" : "h-full overflow-y-auto"}>
      {!compact && (
        <div className="p-6 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-indigo-600/20 flex items-center justify-center">
              <Shield size={24} className="text-indigo-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">信任报告</h1>
              <p className="text-sm text-gray-400 mt-1">
                了解 AI 如何使用你的数据，确保一切可审计、可追溯
              </p>
            </div>
          </div>
        </div>
      )}

      <div className={compact ? "space-y-8" : "p-6 space-y-8"}>
        {compact && (
          <p className="text-sm text-gray-500">了解 AI 如何使用你的数据，确保一切可审计、可追溯</p>
        )}

        {actionError && data && (
          <div className="flex items-center gap-2 text-sm text-red-400 bg-red-950/20 border border-red-900/40 rounded-lg px-3 py-2">
            <AlertCircle size={14} />
            {actionError}
          </div>
        )}

        {/* 数据存储位置 */}
        <section>
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Database size={20} className="text-indigo-400" />
            数据存储位置
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <Kv
              icon={Database}
              label="存储位置"
              value="本地 (SQLite + Chroma)"
              color="text-indigo-400"
              sub="数据永不出本机"
            />
            <Kv
              icon={FileText}
              label="事件日志"
              value={`${sov?.total_events ?? data?.system?.event_log ?? 0} 条`}
              color="text-amber-400"
              sub="append-only · 不可改写"
            />
            <Kv
              icon={MessageSquare}
              label="对话数"
              value={`${data?.system?.conversations ?? 0}`}
              color="text-emerald-400"
              sub={`${data?.system?.messages ?? 0} 条消息`}
            />
            <Kv
              icon={Brain}
              label="记忆"
              value={`${data?.system?.memories ?? 0} 条`}
              color="text-purple-400"
              sub={`${data?.memory?.recent_7d ?? 0} 条近 7 天`}
            />
            <Kv
              icon={Target}
              label="目标"
              value={`${sov?.goals_active ?? 0} 活跃 / ${sov?.total_goals ?? data?.system?.goals ?? 0} 总计`}
              color="text-green-400"
              sub={`${sov?.goals_completed ?? 0} 已完成`}
            />
            <Kv
              icon={Download}
              label="数据导出"
              value="支持完整导出"
              color="text-blue-400"
              sub="一键导出 JSON"
            />
          </div>
        </section>

        {/* AI 做了什么 */}
        <section>
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Activity size={20} className="text-amber-400" />
            AI 做了什么
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <Kv
              icon={Cpu}
              label="LLM 调用 (7天)"
              value={`${tc} 次`}
              color="text-cyan-400"
              sub={`成功率 ${rate}%`}
            />
            <Kv
              icon={Activity}
              label="总成本"
              value={`$${tcost.toFixed(4)}`}
              color="text-amber-400"
              sub={`平均 ${alat.toFixed(0)}ms`}
            />
            <Kv
              icon={Target}
              label="工具调用"
              value={`${data?.tools?.reduce((s, t) => s + (t.total_calls || 0), 0) ?? 0} 次`}
              color="text-purple-400"
              sub={`${data?.tools?.length ?? 0} 种工具`}
            />
            <Kv
              icon={AlertTriangle}
              label="任务队列"
              value={`${data?.health?.task_queue_length ?? 0} 个`}
              color="text-orange-400"
              sub={`LLM 失败率 ${((data?.health?.llm_failure_rate_24h ?? 0) * 100).toFixed(1)}%`}
            />
          </div>
          {(data?.costByModel?.length ?? 0) > 0 && (
            <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4">
              <h3 className="text-sm font-medium text-white mb-3">按模型拆分</h3>
              <div className="space-y-2">
                {data!.costByModel.map((m, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span className="text-gray-400">
                      {m.provider}/{m.model}
                    </span>
                    <div className="flex items-center gap-4">
                      <span className="text-gray-500 text-xs">{m.total_calls} 次</span>
                      <span className="text-gray-300">${m.cost.toFixed(4)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* 记忆索引修复 */}
        {failedRepairCount > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <AlertCircle size={20} className="text-red-400" />
              记忆索引修复失败
              <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">
                {failedRepairCount}
              </span>
            </h2>
            <div className="space-y-2">
              {failedRepairs.map((repair) => (
                <div
                  key={repair.id}
                  className="flex items-start gap-3 bg-red-950/20 border border-red-900/40 rounded-xl p-4"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white font-mono truncate">{repair.aggregate_id}</p>
                    <p className="text-xs text-gray-400 mt-1">
                      {repair.event_type} · seq {repair.event_seq} · 已重试 {repair.retry_count} 次
                    </p>
                    {repair.error && (
                      <p className="text-xs text-red-300 mt-2 break-words">{repair.error}</p>
                    )}
                  </div>
                  <button
                    type="button"
                    aria-label="重试索引"
                    disabled={retryingId === repair.id}
                    onClick={() => void handleRetryRepair(repair.id)}
                    className="shrink-0 px-3 py-1.5 text-xs bg-red-600/20 text-red-300 rounded-lg hover:bg-red-600/30 disabled:opacity-50"
                  >
                    {retryingId === repair.id ? "重试中…" : "重试索引"}
                  </button>
                </div>
              ))}
            </div>
            {(data?.memoryIndexRepairs?.pending ?? 0) > 0 && (
              <p className="text-xs text-gray-500 mt-3">
                另有 {data!.memoryIndexRepairs.pending} 条修复任务排队中
              </p>
            )}
          </section>
        )}

        {/* 需要审批 */}
        <section>
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <AlertTriangle size={20} className="text-red-400" />
            需要审批
            {pendingCount > 0 && (
              <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">
                {pendingCount}
              </span>
            )}
          </h2>
          {pendingCount === 0 ? (
            <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-6 text-center">
              <Shield size={24} className="text-emerald-400 mx-auto mb-2" />
              <p className="text-sm text-gray-400">没有等待审批的操作</p>
              <p className="text-xs text-gray-500 mt-1">AI 没有背着你做任何需要你确认的事</p>
            </div>
          ) : (
            <div className="space-y-2">
              {data!.approvals.map((a) => {
                const fm = FLOW_LABELS[a.flow_type] ?? {
                  label: a.flow_type,
                  color: "text-gray-400",
                };
                return (
                  <div
                    key={a.id}
                    className="flex items-center gap-3 bg-gray-800/50 border border-gray-700/50 rounded-xl p-4 hover:border-gray-600/50 transition-colors"
                  >
                    <div className="w-2 h-2 rounded-full bg-red-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-white truncate">{a.action ?? "未知操作"}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-xs ${fm.color}`}>{fm.label}</span>
                        {a.flow_label && (
                          <span className="text-xs text-gray-500 truncate">{a.flow_label}</span>
                        )}
                      </div>
                    </div>
                    {a.expires_at && (
                      <span className="text-xs text-gray-500 shrink-0">
                        过期: {new Date(a.expires_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* 治理活动统计 (7天) */}
        {data?.governance &&
          (() => {
            const g = data.governance;
            const topTools = Object.entries(g.by_tool || {})
              .sort((a, b) => b[1] - a[1])
              .slice(0, 6);
            const deniedTools = Object.entries(g.denied_tools || {});
            return (
              <section>
                <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <Shield size={20} className="text-purple-400" />
                  治理活动（近 {g.window_days} 天）
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <Kv
                    icon={Activity}
                    label="工具调用"
                    value={`${g.tools_invoked}`}
                    color="text-cyan-400"
                  />
                  <Kv
                    icon={AlertTriangle}
                    label="被拦截"
                    value={`${g.tools_denied}`}
                    color="text-red-400"
                    sub="高风险写操作"
                  />
                  <Kv
                    icon={Shield}
                    label="提交审批"
                    value={`${g.tools_deferred}`}
                    color="text-amber-400"
                    sub={`${g.approvals_approved} 通过 / ${g.approvals_rejected} 拒绝`}
                  />
                  <Kv
                    icon={AlertCircle}
                    label="Taint 升级"
                    value={`${g.taint_elevated}`}
                    color="text-orange-400"
                    sub="外部内容污染链"
                  />
                </div>
                {(topTools.length > 0 || deniedTools.length > 0) && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {topTools.length > 0 && (
                      <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4">
                        <h3 className="text-sm font-medium text-white mb-3">最常用工具</h3>
                        <div className="space-y-1.5">
                          {topTools.map(([name, count]) => (
                            <div key={name} className="flex items-center justify-between text-xs">
                              <span className="text-gray-400 truncate">{name}</span>
                              <span className="text-gray-300">{count}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {deniedTools.length > 0 && (
                      <div className="bg-gray-800/50 border border-red-900/30 rounded-xl p-4">
                        <h3 className="text-sm font-medium text-red-400 mb-3">被拦截工具</h3>
                        <div className="space-y-1.5">
                          {deniedTools.map(([name, count]) => (
                            <div key={name} className="flex items-center justify-between text-xs">
                              <span className="text-gray-400 truncate">{name}</span>
                              <span className="text-red-300">{count} 次拦截</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
                {g.tools_invoked === 0 && (
                  <p className="text-sm text-gray-500">近期无工具调用记录</p>
                )}
              </section>
            );
          })()}
      </div>
    </div>
  );
}

/** Legacy route — redirect into Dashboard trust tab. */
export default function TrustReportPage() {
  return <Navigate to="/dashboard?tab=trust" replace />;
}

function Kv({
  icon: Icon,
  label,
  value,
  sub,
  color,
}: {
  icon: typeof Shield;
  label: string;
  value: string;
  sub?: string;
  color: string;
}) {
  return (
    <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4 hover:border-gray-600/50 transition-colors">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={18} className={color} />
        <h3 className="text-xs text-gray-500">{label}</h3>
      </div>
      <p className="text-xl font-semibold text-white">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}
