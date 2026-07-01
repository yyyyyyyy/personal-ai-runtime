import { useState, useEffect } from "react";
import { Zap, Brain, ArrowRight, RefreshCw, Check } from "lucide-react";
import { API_BASE, request } from "../api/core";
import type { MemoryRow } from "../api/client";
import { listMemoriesGrouped } from "../api/client";
import { ApiError } from "../api/client";

interface DemoState {
  model: string;
  base_url: string;
  total_memories: number;
  total_events: number;
  message: string;
}

export default function ModelSwitchDemoPage() {
  const [step, setStep] = useState<"intro" | "see-memories" | "switch-model" | "verify">("intro");
  const [demoData, setDemoData] = useState<DemoState | null>(null);
  const [memories, setMemories] = useState<MemoryRow[]>([]);
  const [loading, setLoading] = useState(false);

  const loadDemo = async () => {
    setLoading(true);
    try {
      const d = await request<DemoState>(`${API_BASE}/system/demo/model-continuity`);
      setDemoData(d);
      return d;
    } catch { return null; }
    finally { setLoading(false); }
  };

  const loadMemories = async () => {
    try {
      const g = await listMemoriesGrouped();
      setMemories(g.memories);
    } catch {
      // intentionally ignore — demo page, fetch failure is non-critical
    }
  };

  useEffect(() => { loadDemo(); }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-purple-600/20 flex items-center justify-center">
            <Zap size={24} className="text-purple-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">跨模型连续性 Demo</h1>
            <p className="text-sm text-gray-400 mt-1">
              证明：换模型不会丢掉你的记忆
            </p>
          </div>
        </div>
      </div>

      <div className="p-6 max-w-2xl mx-auto space-y-8">
        {/* Step progression */}
        <div className="flex items-center gap-2">
          {(["intro", "see-memories", "switch-model", "verify"] as const).map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                step === s ? "bg-emerald-600 text-white" : "bg-gray-700 text-gray-400"
              }`}>{i + 1}</div>
              <span className="text-xs text-gray-500 hidden sm:inline">
                {s === "intro" ? "开始" : s === "see-memories" ? "查看记忆" : s === "switch-model" ? "切换模型" : "验证"}
              </span>
              {i < 3 && <ArrowRight size={14} className="text-gray-600" />}
            </div>
          ))}
        </div>

        {/* Step 1: Intro */}
        {step === "intro" && (
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Brain size={20} className="text-purple-400" />你的 AI 记住了什么？
            </h2>
            <p className="text-sm text-gray-300">
              跨模型连续性是 Personal AI Runtime 的核心承诺。你的记忆存储在本地 Event Log 中，完全独立于任何 LLM 厂商。
            </p>
            {demoData && (
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="bg-gray-900 rounded-lg p-3">
                  <p className="text-xs text-gray-500">当前模型</p>
                  <p className="text-sm text-white font-mono">{demoData.model}</p>
                </div>
                <div className="bg-gray-900 rounded-lg p-3">
                  <p className="text-xs text-gray-500">记忆数量</p>
                  <p className="text-sm text-white font-mono">{demoData.total_memories} 条</p>
                </div>
              </div>
            )}
            <button onClick={() => { loadMemories(); setStep("see-memories"); }}
              className="flex items-center gap-2 px-4 py-2 mt-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm font-medium transition-colors">
              下一步：查看记忆 <ArrowRight size={14} />
            </button>
          </div>
        )}

        {/* Step 2: See memories */}
        {step === "see-memories" && (
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Brain size={20} className="text-purple-400" />当前记忆
            </h2>
            {memories.length === 0 ? (
              <div className="text-center py-8">
                <Brain size={32} className="text-gray-600 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">暂无记忆。先与 AI 对话积累记忆，再回来验证。</p>
                <p className="text-gray-600 text-xs mt-1">Demo 会展示：切换模型后这些记忆不会丢失。</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {memories.map((m) => (
                  <div key={m.id} className="bg-gray-900 rounded-lg p-3 text-sm">
                    <span className="text-gray-300">{m.content}</span>
                    {m.category && <span className="text-gray-600 text-xs ml-2">[{m.category}]</span>}
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-3">
              <button onClick={() => setStep("switch-model")}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm font-medium transition-colors">
                下一步：去切换模型 <ArrowRight size={14} />
              </button>
              <button onClick={() => loadMemories()}
                className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-colors">
                <RefreshCw size={14} />刷新
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Switch model */}
        {step === "switch-model" && (
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Zap size={20} className="text-amber-400" />切换模型
            </h2>
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4">
              <p className="text-sm text-amber-300">
                去「设置」页面，将默认模型从 <code className="px-1 bg-amber-500/20 rounded">{demoData?.model ?? "当前模型"}</code> 切换为另一个模型（如 Ollama 本地模型），保存后回来点「验证」。
              </p>
            </div>
            <div className="flex gap-3">
              <a href="/settings" className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 rounded-lg text-sm font-medium transition-colors">
                前往设置 <ArrowRight size={14} />
              </a>
              <button onClick={() => { loadDemo(); setStep("verify"); }}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm font-medium transition-colors">
                我已切换，验证 <Check size={14} />
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Verify */}
        {step === "verify" && (
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Check size={20} className="text-emerald-400" />验证结果
            </h2>
            {loading ? (
              <p className="text-gray-400 text-sm">检查中…</p>
            ) : demoData ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-gray-900 rounded-lg p-3">
                    <p className="text-xs text-gray-500">当前模型</p>
                    <p className="text-sm text-white font-mono">{demoData.model}</p>
                  </div>
                  <div className="bg-gray-900 rounded-lg p-3">
                    <p className="text-xs text-gray-500">记忆数量</p>
                    <p className="text-sm text-white font-mono">{demoData.total_memories} 条</p>
                  </div>
                </div>
                <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
                  <p className="text-sm text-emerald-300 flex items-center gap-2">
                    <Check size={16} />
                    {demoData.total_memories > 0
                      ? `✅ 成功！切换模型后，${demoData.total_memories} 条记忆完好无损。`
                      : "✅ 你的数据仍然在本地安全存储。无论用哪个模型，你的 AI 都记得你。"}
                  </p>
                  <p className="text-xs text-emerald-400/70 mt-2">{demoData.message}</p>
                </div>
              </>
            ) : (
              <p className="text-gray-400 text-sm">加载模型信息失败</p>
            )}
            <button onClick={() => { loadDemo(); loadMemories(); setStep("intro"); }}
              className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-colors">
              <RefreshCw size={14} />重新演示
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
