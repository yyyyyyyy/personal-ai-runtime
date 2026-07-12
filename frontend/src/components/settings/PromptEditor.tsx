import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getPromptConfig, updatePromptConfig } from "../../api/client";
import { useErrorStore } from "../../stores/errorStore";
import { usePromptConfigQuery } from "../../hooks/useSettingsQuery";
import { queryKeys } from "../../hooks/useWsInvalidationBridge";

export default function PromptEditor() {
  const addError = useErrorStore((s) => s.addError);
  const queryClient = useQueryClient();
  const { data: cfg, isLoading, error } = usePromptConfigQuery();
  const [identity, setIdentity] = useState("");
  const [codingRules, setCodingRules] = useState("");
  const [isCustomIdentity, setIsCustomIdentity] = useState(false);
  const [isCustomCodingRules, setIsCustomCodingRules] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (error) {
      addError(error instanceof Error ? error.message : "加载人设配置失败", "设置");
    }
  }, [error, addError]);

  useEffect(() => {
    if (cfg && !hydrated) {
      setIdentity(cfg.identity);
      setCodingRules(cfg.coding_rules);
      setIsCustomIdentity(cfg.is_custom_identity);
      setIsCustomCodingRules(cfg.is_custom_coding_rules);
      setHydrated(true);
    }
  }, [cfg, hydrated]);

  const handleSave = async (field: "identity" | "coding_rules") => {
    setSaving(true);
    setMessage("");
    try {
      const payload = field === "identity" ? { identity } : { coding_rules: codingRules };
      await updatePromptConfig(payload);
      if (field === "identity") setIsCustomIdentity(!!identity.trim());
      if (field === "coding_rules") setIsCustomCodingRules(!!codingRules.trim());
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptConfig });
      setMessage("已保存");
      setTimeout(() => setMessage(""), 2000);
    } catch {
      setMessage("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async (field: "identity" | "coding_rules") => {
    setSaving(true);
    setMessage("");
    try {
      await updatePromptConfig({ [field]: "" });
      const next = await getPromptConfig();
      if (field === "identity") {
        setIdentity(next.identity);
        setIsCustomIdentity(false);
      }
      if (field === "coding_rules") {
        setCodingRules(next.coding_rules);
        setIsCustomCodingRules(false);
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptConfig });
      setMessage("已重置为默认");
      setTimeout(() => setMessage(""), 2000);
    } catch {
      setMessage("重置失败");
    } finally {
      setSaving(false);
    }
  };

  if (isLoading && !hydrated) {
    return <p className="text-xs text-gray-600">加载人设中…</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs text-gray-400">
            身份定义 {isCustomIdentity && <span className="text-emerald-400">(已自定义)</span>}
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => handleReset("identity")}
              disabled={saving || !isCustomIdentity}
              className="text-xs text-gray-600 hover:text-gray-400 disabled:opacity-30"
            >
              重置
            </button>
            <button
              onClick={() => handleSave("identity")}
              disabled={saving}
              className="text-xs px-2 py-0.5 bg-emerald-600 hover:bg-emerald-700 rounded text-white disabled:opacity-50"
            >
              保存
            </button>
          </div>
        </div>
        <textarea
          value={identity}
          onChange={(e) => setIdentity(e.target.value)}
          rows={6}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 font-mono focus:border-emerald-500 focus:outline-none resize-y"
          placeholder="定义 AI 的身份、性格、行为准则..."
        />
      </div>
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs text-gray-400">
            代码规则 {isCustomCodingRules && <span className="text-emerald-400">(已自定义)</span>}
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => handleReset("coding_rules")}
              disabled={saving || !isCustomCodingRules}
              className="text-xs text-gray-600 hover:text-gray-400 disabled:opacity-30"
            >
              重置
            </button>
            <button
              onClick={() => handleSave("coding_rules")}
              disabled={saving}
              className="text-xs px-2 py-0.5 bg-emerald-600 hover:bg-emerald-700 rounded text-white disabled:opacity-50"
            >
              保存
            </button>
          </div>
        </div>
        <textarea
          value={codingRules}
          onChange={(e) => setCodingRules(e.target.value)}
          rows={6}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 font-mono focus:border-emerald-500 focus:outline-none resize-y"
          placeholder="定义 AI 编码时的行为规则..."
        />
      </div>
      {message && (
        <p className={`text-xs ${message.includes("失败") ? "text-red-400" : "text-emerald-400"}`}>
          {message}
        </p>
      )}
    </div>
  );
}
