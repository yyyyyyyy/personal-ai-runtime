import { useState, useEffect } from "react";
import { Plug, Check, X, Loader2, RefreshCw, Globe, Calendar, Mail, Cpu } from "lucide-react";
import { API_BASE, request } from "../api/core";

interface ConnectorInfo {
  name: string;
  type: string;
  icon?: string;
  status: string;
  tools: string[];
  description?: string;
}

export default function IntegrationsHubPage() {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    request<{ connectors: ConnectorInfo[] }>(`${API_BASE}/connectors/`)
      .then((r) => setConnectors(r.connectors))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const iconMap: Record<string, typeof Plug> = {
    mail: Mail,
    calendar: Calendar,
    brave: Globe,
    github: Cpu,
    notion: Cpu,
    tavily: Globe,
  };

  if (loading)
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={32} className="animate-spin text-gray-400" />
      </div>
    );

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <Plug size={24} className="text-cyan-400" />
          <div>
            <h1 className="text-xl font-bold text-white">集成中心</h1>
            <p className="text-sm text-gray-400 mt-1">连接外部服务，扩展 AI 能力</p>
          </div>
        </div>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {connectors.map((c) => {
            const Icon = iconMap[c.name] ?? Plug;
            const online = c.status === "online" || c.status === "connected";
            const nameMap: Record<string, string> = {
              mail: "邮箱",
              calendar: "日历",
              brave: "Brave 搜索",
              github: "GitHub",
              notion: "Notion",
              tavily: "Tavily",
            };
            return (
              <div key={c.name} className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <Icon size={24} className="text-cyan-400" />
                    <div>
                      <h3 className="text-white font-medium">{nameMap[c.name] ?? c.name}</h3>
                      <p className="text-xs text-gray-500">{c.type}</p>
                    </div>
                  </div>
                  <span
                    className={`flex items-center gap-1 text-xs px-2 py-1 rounded-full ${
                      online ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"
                    }`}
                  >
                    {online ? <Check size={10} /> : <X size={10} />}
                    {online ? "已连接" : "未连接"}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {c.tools.slice(0, 5).map((t) => (
                    <span
                      key={t}
                      className="text-[10px] bg-gray-700 px-1.5 py-0.5 rounded text-gray-400"
                    >
                      {t}
                    </span>
                  ))}
                  {c.tools.length > 5 && (
                    <span className="text-[10px] text-gray-500">+{c.tools.length - 5}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {connectors.length === 0 && (
          <p className="text-gray-500 text-center py-12">暂无连接器。在设置中配置 MCP 服务器。</p>
        )}
      </div>
    </div>
  );
}
