import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE, request } from "../api/core";

interface Template {
  id: string; name: string; icon: string; description: string; category: string;
  nodes: unknown[]; edges?: unknown[];
}

export default function SceneTemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [creating, setCreating] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    request<{ templates: Template[] }>(`${API_BASE}/workflows/templates`).then(r => setTemplates(r.templates)).catch(() => {});
  }, []);

  const instantiate = async (t: Template) => {
    setCreating(t.id);
    try {
      const r = await request<{ id: string }>(`${API_BASE}/workflows/from-template/${t.id}`, { method: "POST" });
      navigate(`/workflows/${r.id}`);
    } catch {}
    setCreating(null);
  };

  const categories = [...new Set(templates.map(t => t.category))];

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 border-b border-gray-800">
        <h1 className="text-xl font-bold text-white">场景模版</h1>
        <p className="text-sm text-gray-400 mt-1">一键创建常用自动化工作流</p>
      </div>
      <div className="p-6 space-y-8">
        {categories.map(cat => (
          <section key={cat}>
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">{cat}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {templates.filter(t => t.category === cat).map(t => (
                <div key={t.id} className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-5 hover:border-emerald-600/40 transition-colors">
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">{t.icon}</span>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-white font-medium">{t.name}</h3>
                      <p className="text-sm text-gray-400 mt-1">{t.description}</p>
                      <p className="text-xs text-gray-600 mt-2">
                        {t.nodes.length} 个节点 · {t.edges?.length ?? t.nodes.length - 1} 条连接
                      </p>
                    </div>
                  </div>
                  <button onClick={() => instantiate(t)} disabled={creating === t.id}
                    className="w-full mt-4 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-700 rounded-lg text-sm font-medium transition-colors">
                    {creating === t.id ? "创建中…" : "使用此模版"}
                  </button>
                </div>
              ))}
            </div>
          </section>
        ))}
        {templates.length === 0 && (
          <p className="text-gray-500 text-center py-12">加载场景模版中…</p>
        )}
      </div>
    </div>
  );
}
