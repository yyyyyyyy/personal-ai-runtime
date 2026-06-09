import { useEffect, useState } from "react";
import {
  getCostSummary,
  getToolSummary,
  getMemoryStats,
  getHealth,
  type CostSummary,
  type ToolSummaryItem,
  type MemoryStats,
  type HealthSnapshot,
} from "../api/client";

function StatCard({ label, value, unit, color }: { label: string; value: string | number; unit?: string; color?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-bold" style={{ color: color || "#10b981" }}>
        {value}
        {unit && <span className="text-sm font-normal text-gray-400 ml-1">{unit}</span>}
      </div>
    </div>
  );
}

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span className="truncate mr-2">{label}</span>
        <span>{value.toLocaleString()}</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function ToolBadge({ tool }: { tool: ToolSummaryItem }) {
  const rate = tool.total_calls > 0 ? ((tool.total_calls - tool.failed_calls) / tool.total_calls * 100).toFixed(0) : "0";
  const color = Number(rate) >= 95 ? "#10b981" : Number(rate) >= 80 ? "#f59e0b" : "#ef4444";
  return (
    <div className="flex items-center justify-between py-2 px-3 bg-gray-800/50 rounded-lg">
      <span className="text-sm text-gray-300">{tool.tool_name}</span>
      <div className="flex items-center gap-3 text-xs">
        <span className="text-gray-500">{tool.total_calls} 次</span>
        <span className="text-gray-500">{(tool.avg_latency_ms || 0).toFixed(0)}ms</span>
        <span style={{ color }}>{rate}%</span>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [tools, setTools] = useState<ToolSummaryItem[]>([]);
  const [memory, setMemory] = useState<MemoryStats | null>(null);
  const [health, setHealth] = useState<HealthSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchData = async () => {
    setLoading(true);
    setError("");
    try {
      const [costData, toolData, memData, healthData] = await Promise.all([
        getCostSummary(7),
        getToolSummary(7),
        getMemoryStats(),
        getHealth(),
      ]);
      setCost(costData);
      setTools(toolData);
      setMemory(memData);
      setHealth(healthData);
    } catch (e) {
      setError("无法连接到后端服务，请确认后端已启动");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

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
          <div className="text-gray-500 mb-2">⚠</div>
          <div className="text-gray-400 mb-4">{error}</div>
          <button
            onClick={fetchData}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm transition-colors"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  const totalTokens = (cost?.total_prompt_tokens || 0) + (cost?.total_completion_tokens || 0);
  const successRate = cost && cost.total_calls > 0
    ? (((cost.total_calls - cost.failed_calls) / cost.total_calls) * 100).toFixed(1)
    : "100";

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-gray-200">系统运行概览</h2>
          <button
            onClick={fetchData}
            className="px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg transition-colors"
          >
            刷新
          </button>
        </div>

        {/* Health Indicators */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          <StatCard
            label="LLM 成功率 (24h)"
            value={`${successRate}%`}
            color={Number(successRate) >= 95 ? "#10b981" : "#f59e0b"}
          />
          <StatCard
            label="任务队列"
            value={health?.task_queue_length ?? 0}
            color={health && health.task_queue_length < 10 ? "#10b981" : "#f59e0b"}
          />
          <StatCard
            label="工具失败率 (24h)"
            value={`${((health?.tool_failure_rate_24h || 0) * 100).toFixed(1)}%`}
            color={(health?.tool_failure_rate_24h || 0) < 0.05 ? "#10b981" : "#ef4444"}
          />
          <StatCard
            label="总记忆数"
            value={memory?.total_memories ?? 0}
            unit="条"
            color="#6366f1"
          />
        </div>

        {/* Cost & Token */}
        <div className="grid grid-cols-2 gap-6 mb-6">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h3 className="text-sm font-medium text-gray-300 mb-4">Token 用量 (7天)</h3>
            <Bar label="输入 Token" value={cost?.total_prompt_tokens || 0} max={totalTokens || 1} color="#3b82f6" />
            <Bar label="输出 Token" value={cost?.total_completion_tokens || 0} max={totalTokens || 1} color="#10b981" />
            <div className="mt-4 pt-3 border-t border-gray-800 flex justify-between text-sm">
              <span className="text-gray-500">总计</span>
              <span className="text-gray-200 font-medium">{totalTokens.toLocaleString()} tokens</span>
            </div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h3 className="text-sm font-medium text-gray-300 mb-4">成本与延迟 (7天)</h3>
            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">预估费用</span>
                <span className="text-sm text-gray-200 font-mono">${(cost?.total_cost || 0).toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">平均延迟</span>
                <span className="text-sm text-gray-200 font-mono">{(cost?.avg_latency_ms || 0).toFixed(0)}ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">总调用次数</span>
                <span className="text-sm text-gray-200 font-mono">{cost?.total_calls || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">失败次数</span>
                <span className="text-sm" style={{ color: (cost?.failed_calls || 0) > 0 ? "#ef4444" : "#10b981" }}>
                  {cost?.failed_calls || 0}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Tool Success Rate */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
          <h3 className="text-sm font-medium text-gray-300 mb-3">工具调用详情 (7天)</h3>
          {tools.length > 0 ? (
            <div className="space-y-1">
              {tools.map((t) => <ToolBadge key={t.tool_name} tool={t} />)}
            </div>
          ) : (
            <p className="text-gray-600 text-sm text-center py-4">暂无工具调用数据</p>
          )}
        </div>

        {/* Memory Stats */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-medium text-gray-300 mb-3">记忆系统</h3>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center py-3">
              <div className="text-2xl font-bold text-indigo-400">{memory?.total_memories || 0}</div>
              <div className="text-xs text-gray-500 mt-1">总记忆</div>
            </div>
            <div className="text-center py-3">
              <div className="text-2xl font-bold text-emerald-400">{memory?.recent_7d || 0}</div>
              <div className="text-xs text-gray-500 mt-1">近7天新增</div>
            </div>
            <div className="text-center py-3">
              <div className="text-2xl font-bold text-amber-400">
                {memory ? Object.keys(memory.categories).length : 0}
              </div>
              <div className="text-xs text-gray-500 mt-1">分类数</div>
            </div>
          </div>
          {memory && Object.keys(memory.categories).length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-800">
              <div className="flex flex-wrap gap-2">
                {Object.entries(memory.categories).map(([cat, count]) => (
                  <span key={cat} className="px-2 py-1 bg-gray-800 rounded text-xs text-gray-400">
                    {cat}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
