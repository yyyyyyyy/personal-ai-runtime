import { useEffect, useState } from "react";
import { installMcpConnector } from "../../api/connectors";
import { useErrorStore } from "../../stores/errorStore";
import { useMcpRegistryQuery } from "../../hooks/useSettingsQuery";

const CATEGORIES: Record<string, string> = {
  browser: "浏览器",
  search: "搜索",
  developer: "开发者",
  productivity: "效率",
  system: "系统",
  ai: "AI",
  communication: "通讯",
};

export default function McpMarketplace() {
  const addError = useErrorStore((s) => s.addError);
  const { data: servers = [], isLoading, error, isFetched } = useMcpRegistryQuery();
  const [installing, setInstalling] = useState<string | null>(null);

  useEffect(() => {
    if (error) {
      addError(error instanceof Error ? error.message : "加载 MCP 市场失败", "设置");
    }
  }, [error, addError]);

  const handleInstall = async (name: string) => {
    setInstalling(name);
    try {
      const data = await installMcpConnector(name);
      if (data.ok) {
        alert(`"${name}" 已安装。重启后端后生效。`);
      } else {
        alert(data.message);
      }
    } catch {
      alert("安装失败");
    } finally {
      setInstalling(null);
    }
  };

  if (isLoading || !isFetched) {
    return <p className="text-xs text-gray-600">加载市场中…</p>;
  }

  return (
    <div className="space-y-2 max-h-60 overflow-y-auto">
      {servers.length === 0 ? (
        <p className="text-xs text-gray-600">暂无可用 MCP 服务器</p>
      ) : (
        servers.map((s) => (
          <div
            key={s.name}
            className="flex items-center justify-between bg-gray-800/50 rounded-lg p-2.5"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-gray-300">{s.name}</span>
                <span className="text-xs px-1.5 py-0.5 bg-gray-700 rounded text-gray-500">
                  {CATEGORIES[s.category] || s.category}
                </span>
              </div>
              <p className="text-xs text-gray-600 mt-0.5 truncate">{s.description}</p>
              {Object.keys(s.env_vars || {}).length > 0 && (
                <p className="text-xs text-gray-700 mt-0.5">
                  需要: {Object.keys(s.env_vars).join(", ")}
                </p>
              )}
            </div>
            <button
              onClick={() => handleInstall(s.name)}
              disabled={installing === s.name || s.installed}
              className={s.installed
                ? "shrink-0 ml-3 px-3 py-1 text-xs bg-gray-800 text-gray-600 rounded cursor-not-allowed"
                : "shrink-0 ml-3 px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors disabled:opacity-50"
              }
            >
              {installing === s.name ? "安装中…" : s.installed ? "已安装" : "安装"}
            </button>
          </div>
        ))
      )}
    </div>
  );
}
