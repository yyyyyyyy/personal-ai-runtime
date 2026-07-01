import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE, request } from "../api/core";
import { Workflow, Plus, Clock, Trash2, Zap, Loader2 } from "lucide-react";

interface WorkflowData {
  id: string;
  name: string;
  description: string;
  nodes: unknown[];
  edges: unknown[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export default function WorkflowListPage() {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<WorkflowData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchWorkflows = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<{ workflows: WorkflowData[] }>(`${API_BASE}/workflows`);
      setWorkflows(data.workflows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWorkflows();
  }, [fetchWorkflows]);

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此工作流？")) return;
    await request(`${API_BASE}/workflows/${id}`, { method: "DELETE" });
    fetchWorkflows();
  };

  const handleCreate = async () => {
    const data = await request<WorkflowData>(`${API_BASE}/workflows`, {
      method: "POST",
      body: JSON.stringify({ name: "新工作流", nodes: [], edges: [] }),
    });
    navigate(`/workflows/${data.id}`);
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-200">工作流</h2>
            <p className="text-sm text-gray-500 mt-0.5">可视化编排 AI 自动化任务</p>
          </div>
          <button
            onClick={handleCreate}
            className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} /> 新建工作流
          </button>
        </div>

        {error && (
          <div className="bg-red-900/20 border border-red-700/50 rounded-lg p-3 mb-4 text-sm text-red-400">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 size={24} className="text-gray-400 animate-spin" />
          </div>
        ) : workflows.length === 0 ? (
          <div className="text-center py-16">
            <Workflow size={48} className="mx-auto mb-3 text-gray-700" />
            <p className="text-gray-500 text-sm mb-3">暂无工作流</p>
            <p className="text-gray-600 text-xs mb-4">
              工作流可以可视化编排 AI 自动化任务，将定时触发、AI 对话、工具调用串联起来。
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {workflows.map((wf) => (
              <div
                key={wf.id}
                onClick={() => navigate(`/workflows/${wf.id}`)}
                className="flex items-center justify-between bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-lg p-3 cursor-pointer group transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Workflow size={18} className="text-emerald-400 shrink-0" />
                  <div className="min-w-0">
                    <div className="text-sm text-gray-300 truncate">{wf.name}</div>
                    <div className="text-xs text-gray-600 mt-0.5">
                      {wf.nodes.length} 个节点 · {wf.edges.length} 条连线
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${wf.enabled ? "bg-emerald-900/30 text-emerald-400" : "bg-gray-800 text-gray-600"}`}
                  >
                    {wf.enabled ? (
                      <Zap size={10} className="inline mr-1" />
                    ) : (
                      <Clock size={10} className="inline mr-1" />
                    )}
                    {wf.enabled ? "启用" : "草稿"}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(wf.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all shrink-0"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
