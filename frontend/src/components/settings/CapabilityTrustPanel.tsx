import { useEffect } from "react";
import { useErrorStore } from "../../stores/errorStore";
import { useCapabilityPolicyQuery } from "../../hooks/useSettingsQuery";
import { toolLabel } from "../../utils/toolLabels";

function ToolChipList({
  tools,
  tone,
}: {
  tools: string[];
  tone: "emerald" | "amber" | "red" | "cyan";
}) {
  const styles = {
    emerald: "bg-emerald-900/20 text-emerald-400/70 border-emerald-700/20",
    amber: "bg-amber-900/20 text-amber-400/70 border-amber-700/20",
    red: "bg-red-900/20 text-red-400/70 border-red-700/20",
    cyan: "bg-cyan-900/20 text-cyan-400/70 border-cyan-700/20",
  }[tone];
  if (tools.length === 0) {
    return <p className="text-xs text-gray-600">（无）</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {tools.map((id) => (
        <span key={id} className={`text-xs px-2 py-1 rounded border ${styles}`} title={id}>
          {toolLabel(id)}
        </span>
      ))}
    </div>
  );
}

export default function CapabilityTrustPanel() {
  const { data, isLoading, error, refetch } = useCapabilityPolicyQuery();
  const addError = useErrorStore((s) => s.addError);

  useEffect(() => {
    if (error) {
      addError(error instanceof Error ? error.message : "加载能力策略失败", "设置");
    }
  }, [error, addError]);

  if (isLoading) {
    return <p className="text-xs text-gray-600">加载策略中…</p>;
  }
  if (!data) {
    return (
      <button
        type="button"
        onClick={() => void refetch()}
        className="text-xs text-emerald-400 hover:text-emerald-300"
      >
        加载失败，点击重试
      </button>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-xs font-medium text-emerald-400">自动执行</span>
          <span className="text-xs text-gray-500">— 安全操作，无需确认</span>
        </div>
        <ToolChipList tools={data.auto_allow} tone="emerald" />
      </div>
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="w-2 h-2 rounded-full bg-amber-500" />
          <span className="text-xs font-medium text-amber-400">需要确认</span>
          <span className="text-xs text-gray-500">— 写操作 / 外发，可在对话内信任</span>
        </div>
        <ToolChipList tools={data.needs_user} tone="amber" />
      </div>
      {data.external_ingestion.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2 h-2 rounded-full bg-cyan-500" />
            <span className="text-xs font-medium text-cyan-400">外部内容摄入</span>
            <span className="text-xs text-gray-500">— 会污染上下文链，后续写操作需确认</span>
          </div>
          <ToolChipList tools={data.external_ingestion} tone="cyan" />
        </div>
      )}
      {data.forbidden.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            <span className="text-xs font-medium text-red-400">禁止</span>
            <span className="text-xs text-gray-500">— 策略硬拦截</span>
          </div>
          <ToolChipList tools={data.forbidden} tone="red" />
        </div>
      )}
    </div>
  );
}
