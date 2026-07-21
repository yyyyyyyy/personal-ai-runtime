import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getSystemHealth, getLlmProviders, createConversation, ApiError } from "../../api/client";
import { useChatStore } from "../../stores/chatStore";
import { useErrorStore } from "../../stores/errorStore";
import { useConversationCacheActions } from "../../hooks/useConversationsQuery";
import Button from "../ui/Button";
import Card from "../ui/Card";

const STEPS = [
  { title: "连接后端", description: "确认 Personal AI Runtime 后端已启动" },
  { title: "配置 AI 大脑", description: "设置 LLM 模型，让 AI 可以思考和对话" },
  { title: "开始第一次对话", description: "选一个话题，立即体验 AI 能为你做什么" },
];

const STARTER_PROMPTS = [
  {
    icon: "🎯",
    label: "帮我规划一个目标",
    prompt: "帮我设定一个这周想完成的目标，拆解成可执行的步骤",
    title: "目标规划",
  },
  {
    icon: "📬",
    label: "总结我的收件箱",
    prompt: "帮我看看收件箱里有什么重要的邮件，总结一下需要我处理的",
    title: "收件箱摘要",
  },
  {
    icon: "🧠",
    label: "记下关于我的事",
    prompt: "我想让你记住一些关于我的事情：我的工作、兴趣和习惯，方便以后更好地帮助我",
    title: "建立记忆",
  },
  { icon: "💬", label: "自由聊几句", prompt: "", title: "新对话" },
];

interface Props {
  onComplete: () => void;
}

export default function OnboardingWizard({ onComplete }: Props) {
  const navigate = useNavigate();
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const setPendingPrompt = useChatStore((s) => s.setPendingPrompt);
  const addError = useErrorStore((s) => s.addError);
  const { upsert } = useConversationCacheActions();

  const [step, setStep] = useState(0);
  const [checking, setChecking] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [message, setMessage] = useState("");
  const [messageOk, setMessageOk] = useState(true);
  const [llmConfigured, setLlmConfigured] = useState(false);

  const checkHealth = async (): Promise<boolean> => {
    setChecking(true);
    try {
      const health = await getSystemHealth();
      setMessage("后端运行正常");
      setMessageOk(true);
      setLlmConfigured(health?.startup?.checks?.llm?.configured ?? false);
      return true;
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "无法连接后端，请先启动服务");
      setMessageOk(false);
      setLlmConfigured(false);
      return false;
    } finally {
      setChecking(false);
    }
  };

  const checkLlm = async (): Promise<boolean> => {
    setChecking(true);
    try {
      const res = await getLlmProviders();
      const count = res.providers?.length ?? 0;
      if (count === 0) {
        setMessage("未检测到 LLM 提供商。无需编辑 .env 文件，在设置中直接配置即可。");
        setMessageOk(false);
        return false;
      }
      setMessage(`已就绪，默认模型：${res.default}`);
      setMessageOk(true);
      return true;
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "检查 LLM 失败");
      setMessageOk(false);
      return false;
    } finally {
      setChecking(false);
    }
  };

  const launchConversation = async (promptText: string, title: string) => {
    setLaunching(true);
    try {
      const conv = await createConversation(title);
      upsert(conv);
      setActiveConversation(conv.id);
      if (promptText) setPendingPrompt(promptText);
      localStorage.setItem("onboarding_done", "1");
      navigate(`/chat/${conv.id}`);
      onComplete();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "创建对话失败";
      addError(msg, "对话");
      setLaunching(false);
    }
  };

  const handleNext = async () => {
    if (step === 0) {
      const ok = await checkHealth();
      if (!ok) return;
      // Auto-advance if LLM is already configured
      if (llmConfigured) {
        setStep(2);
        setMessage("");
        return;
      }
      setStep(1);
      setMessage("");
      return;
    }
    if (step === 1) {
      const ok = await checkLlm();
      if (!ok) return;
      setStep(2);
      setMessage("");
      return;
    }
    localStorage.setItem("onboarding_done", "1");
    onComplete();
  };

  const goToSettings = () => {
    localStorage.setItem("onboarding_done", "1");
    onComplete();
    navigate("/settings");
  };

  const current = STEPS[step];

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 p-4">
      <Card className="max-w-md w-full">
        <div className="text-xs text-emerald-500 mb-2">
          首次引导 {step + 1}/{STEPS.length}
        </div>
        <h2 className="text-xl font-semibold text-gray-100">{current.title}</h2>
        <p className="text-sm text-gray-400 mt-2">{current.description}</p>

        {step < 2 && (
          <div className="mt-4">
            <Button
              size="sm"
              variant="secondary"
              onClick={step === 0 ? checkHealth : checkLlm}
              disabled={checking}
            >
              {checking ? "检查中…" : "运行检查"}
            </Button>
            {message && (
              <p className={`text-xs mt-2 ${messageOk ? "text-emerald-400" : "text-red-400"}`}>
                {message}
              </p>
            )}
            {step === 1 && !messageOk && !checking && (
              <div className="mt-3 p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                <p className="text-xs text-amber-300 mb-2">
                  推荐使用 DeepSeek（注册即送免费额度），或在设置中添加你想用的任何兼容 OpenAI API
                  的模型。
                </p>
                <Button size="sm" variant="secondary" onClick={goToSettings}>
                  前往设置页面配置
                </Button>
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-gray-500 mb-3">一切就绪。选一个开始——你的 AI 会立即响应：</p>
            {STARTER_PROMPTS.map((sp) => (
              <button
                key={sp.label}
                type="button"
                onClick={() => launchConversation(sp.prompt, sp.title)}
                disabled={launching}
                className="w-full flex items-center gap-3 p-3 bg-gray-800/50 hover:bg-gray-800 border border-gray-700/50 hover:border-emerald-600/40 rounded-lg text-left transition-colors disabled:opacity-50"
              >
                <span className="text-xl">{sp.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-200">{sp.label}</div>
                  {sp.prompt && (
                    <div className="text-xs text-gray-500 truncate mt-0.5">{sp.prompt}</div>
                  )}
                </div>
              </button>
            ))}
            {launching && (
              <p className="text-xs text-emerald-400 text-center pt-2">正在开启对话…</p>
            )}
          </div>
        )}

        <div className="flex justify-between mt-6">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              localStorage.setItem("onboarding_done", "1");
              onComplete();
            }}
          >
            {step === 2 ? "稍后再说" : "跳过"}
          </Button>
          {step < 2 && (
            <Button size="sm" onClick={handleNext} disabled={checking}>
              下一步
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
