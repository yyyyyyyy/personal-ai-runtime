import { Navigate } from "react-router-dom";
import {
  User,
  Heart,
  Target,
  Users,
  Dumbbell,
  Wallet,
  Briefcase,
  Sparkles,
  AlertCircle,
  Loader2,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import { usePortraitQuery } from "../hooks/usePortraitQuery";

const CATEGORY_META: Record<string, { label: string; icon: typeof User; description: string }> = {
  preferences: { label: "偏好", icon: Heart, description: "你的喜好与倾向" },
  values: { label: "价值观", icon: Sparkles, description: "你的信念与原则" },
  relationships: { label: "关系", icon: Users, description: "你的人际关系网络" },
  health: { label: "健康", icon: Dumbbell, description: "你的身心健康" },
  finance: { label: "财务", icon: Wallet, description: "你的财务相关" },
  career: { label: "职业", icon: Briefcase, description: "你的职业发展" },
};

function confidenceLevel(score: number): { color: string; label: string; pct: number } {
  const pct = Math.round(score * 100);
  if (pct >= 80) return { color: "bg-emerald-500", label: "高可信", pct };
  if (pct >= 50) return { color: "bg-amber-500", label: "中等可信", pct };
  return { color: "bg-red-500", label: "低可信", pct };
}

/** Portrait content — embedded as a Memories tab; also used by tests. */
export function PortraitPanel({ compact = false }: { compact?: boolean }) {
  const { data, isLoading: loading, error: queryError, refetch } = usePortraitQuery();
  const error = queryError instanceof Error ? queryError.message : queryError ? String(queryError) : null;

  if (loading) {
    return (
      <div className={`flex items-center justify-center ${compact ? "py-16" : "h-full"}`}>
        <div className="flex flex-col items-center gap-3 text-gray-400">
          <Loader2 size={32} className="animate-spin" />
          <p className="text-sm">正在生成你的 AI 画像…</p>
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
            onClick={() => void refetch()}
            className="flex items-center gap-2 px-4 py-2 mt-2 text-sm bg-emerald-600/20 text-emerald-400 rounded-lg hover:bg-emerald-600/30 transition-colors"
          >
            <RefreshCw size={14} />
            重试
          </button>
        </div>
      </div>
    );
  }

  const profileEntries = Object.entries(data?.profile ?? {});
  const totalItems =
    profileEntries.length + (data?.habits?.length ?? 0) + (data?.goals?.length ?? 0);

  return (
    <div className={compact ? "" : "h-full overflow-y-auto"}>
      {!compact && (
        <div className="p-6 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-emerald-600/20 flex items-center justify-center">
              <User size={24} className="text-emerald-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">AI 画像</h1>
              <p className="text-sm text-gray-400 mt-1">AI 对你的理解——包含 {totalItems} 项洞察</p>
            </div>
          </div>
        </div>
      )}

      <div className={compact ? "space-y-8" : "p-6 space-y-8"}>
        {compact && (
          <p className="text-sm text-gray-500">AI 对你的理解——包含 {totalItems} 项洞察</p>
        )}

        {error && data && (
          <div className="flex items-center gap-2 text-sm text-amber-400 bg-amber-950/20 border border-amber-900/40 rounded-lg px-3 py-2">
            <AlertCircle size={14} />
            刷新失败：{error}
            <button type="button" onClick={() => void refetch()} className="underline ml-auto">
              重试
            </button>
          </div>
        )}

        {totalItems === 0 && (
          <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20">
            <AlertCircle size={20} className="text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-amber-300 text-sm font-medium">画像尚未建立</p>
              <p className="text-amber-400/70 text-xs mt-1">
                与 AI 多聊几次后，它会逐渐了解你的偏好、习惯和目标。
                <br />
                新用户通常在 5 分钟内看到自己的初始画像。
              </p>
            </div>
          </div>
        )}

        {profileEntries.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <User size={20} className="text-emerald-400" />
              用户画像
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {profileEntries.map(([category, item]) => {
                if (!item) return null;
                const meta = CATEGORY_META[category] ?? {
                  label: category,
                  icon: User,
                  description: "",
                };
                const Icon = meta.icon;
                const conf = confidenceLevel(item.confidence);
                return (
                  <div
                    key={category}
                    className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4 hover:border-gray-600/50 transition-colors"
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <Icon size={18} className="text-emerald-400" />
                      <h3 className="text-sm font-medium text-white">{meta.label}</h3>
                    </div>
                    <div className="space-y-2">
                      {Object.entries(item.data).map(([key, value]) => (
                        <div key={key} className="text-sm">
                          <span className="text-gray-500">{key}：</span>
                          <span className="text-gray-200">{String(value)}</span>
                        </div>
                      ))}
                      {Object.keys(item.data).length === 0 && (
                        <p className="text-xs text-gray-500">暂无数据</p>
                      )}
                    </div>
                    <div className="mt-3 pt-3 border-t border-gray-700/50">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${conf.color}`}
                            style={{ width: `${conf.pct}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500">{conf.pct}%</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {(data?.habits?.length ?? 0) > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <RefreshCw size={20} className="text-blue-400" />
              习惯
            </h2>
            <div className="space-y-2">
              {data!.habits.map((habit) => {
                const conf = confidenceLevel(habit.confidence);
                return (
                  <div
                    key={habit.id}
                    className="flex items-start gap-4 bg-gray-800/50 border border-gray-700/50 rounded-xl p-4 hover:border-gray-600/50 transition-colors"
                  >
                    <ChevronRight size={18} className="text-blue-400 mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-200">{habit.content}</p>
                      <div className="flex items-center gap-3 mt-2">
                        <div className="flex items-center gap-1.5">
                          <div className={`w-2 h-2 rounded-full ${conf.color}`} />
                          <span className="text-xs text-gray-500">{conf.label}</span>
                        </div>
                        <span className="text-xs text-gray-600">
                          {habit.origin === "self_report" ? "来自你的告知" : "AI 推断"}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {(data?.goals?.length ?? 0) > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Target size={20} className="text-purple-400" />
              当前目标
            </h2>
            <div className="space-y-3">
              {data!.goals.map((goal) => (
                <div
                  key={goal.id}
                  className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4 hover:border-gray-600/50 transition-colors"
                >
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-medium text-white">{goal.title}</h3>
                    <span className="text-xs text-purple-400">
                      {goal.progress > 0 ? `${goal.progress}%` : "待开始"}
                    </span>
                  </div>
                  {goal.progress > 0 && (
                    <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-purple-500 rounded-full transition-all"
                        style={{ width: `${goal.progress}%` }}
                      />
                    </div>
                  )}
                  {goal.deadline && (
                    <p className="text-xs text-gray-500 mt-2">截止: {goal.deadline}</p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

/** Legacy route — redirect into Memories portrait tab. */
export default function PortraitPage() {
  return <Navigate to="/memories?tab=portrait" replace />;
}
