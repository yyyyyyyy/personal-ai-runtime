import { useState, useEffect, useRef, useCallback } from "react";
import { Zap, MailSearch, Target as TargetIcon, BrainCircuit, Lightbulb } from "lucide-react";
import { type MemoryRow } from "../../api/client";
import { type StreamEvent } from "../../api/client";
import { listWorkItems } from "../../api/workItems";
import { useErrorStore } from "../../stores/errorStore";
import { useChatStore } from "../../stores/chatStore";
import { useChatMessages } from "../../hooks/useChatMessages";
import { useApprovalFlow } from "../../hooks/useApprovalFlow";
import { useMemoriesGroupedQuery } from "../../hooks/useMemoriesQuery";
import MessageItem from "./MessageItem";
import ConfirmationDialog from "./ConfirmationDialog";
import ContextPanel from "./ContextPanel";
import VoiceInput from "./VoiceInput";

interface Props {
  conversationId: string;
}

const SUGGESTION_META: Record<
  string,
  { icon: React.ComponentType<{ size?: number; className?: string }> }
> = {
  目标: { icon: TargetIcon },
  收件箱: { icon: MailSearch },
  对话: { icon: BrainCircuit },
  规划: { icon: Lightbulb },
};

const CAPABILITY_CHIPS: Array<{ icon: string; label: string; prompt: string }> = [
  { icon: "📄", label: "读写文件", prompt: "帮我在桌面创建一个 todo.md，列出今天的任务" },
  { icon: "🌐", label: "搜索网页", prompt: "帮我搜索最新的 Python 3.13 特性并总结" },
  { icon: "📬", label: "处理邮件", prompt: "帮我看看收件箱有什么重要的邮件" },
  { icon: "📅", label: "管理日程", prompt: "我这周有什么日历日程？" },
  { icon: "🎯", label: "规划目标", prompt: "帮我设定一个本周目标并拆解步骤" },
  { icon: "🧠", label: "记住信息", prompt: "我想让你记住一些关于我的事情" },
];

function getSuggestionIcon(label: string) {
  for (const [key, meta] of Object.entries(SUGGESTION_META)) {
    if (label.includes(key)) return meta.icon;
  }
  return Zap;
}

export default function ChatView({ conversationId }: Props) {
  const [input, setInput] = useState("");
  const [contextOpen, setContextOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [memoryNotice, setMemoryNotice] = useState<string | null>(null);
  const [initialLoad, setInitialLoad] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const prevMemoryTotalRef = useRef<number | null>(null);

  const addError = useErrorStore((s) => s.addError);
  const handleVoiceTranscript = useCallback((transcript: string) => {
    setInput((prev) => (prev ? prev + " " + transcript : transcript));
    inputRef.current?.focus();
  }, []);
  const pendingPrompt = useChatStore((s) => s.pendingPrompt);
  const setPendingPrompt = useChatStore((s) => s.setPendingPrompt);

  // Server state lives in TanStack Query; cache is invalidated by WS
  // `memory_changed` events so we never need setTimeout polling.
  const { data: memData } = useMemoriesGroupedQuery();
  const recentMemories: MemoryRow[] = memData?.recent ?? [];
  const memoryTotal: number = memData?.memories.length ?? 0;
  // Track whether the user has sent at least one message in this session
  // — only then do we want "I just remembered" toasts. Initial cache load
  // must not fire a toast, and StrictMode double-invocation must not either.
  const hasSentRef = useRef(false);

  const {
    messages,
    setMessages,
    isLoading,
    streamingContent,
    handleSend: sendMessageBase,
    lastUserMessage,
    allToolResults,
  } = useChatMessages(conversationId, addError);

  const { pendingConfirmation, setFromEvent, confirm, deny } = useApprovalFlow(conversationId);

  const adjustTextareaHeight = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => {
    adjustTextareaHeight();
  }, [input, adjustTextareaHeight]);

  useEffect(() => {
    if (pendingPrompt) {
      setInput(pendingPrompt);
      setPendingPrompt(null);
      adjustTextareaHeight();
    }
  }, [pendingPrompt, setPendingPrompt, adjustTextareaHeight]);

  // Read memories via ref so WS `memory_changed` (which changes memData
  // identity every time) does NOT re-create this callback or re-fetch goals —
  // preventing request storms when the Pattern Aggregator emits many
  // MemoryDerived events in quick succession.
  const memDataRef = useRef(memData);
  memDataRef.current = memData;
  // One-shot: if the first suggestions load raced ahead of the memories
  // query, re-run once when memData first arrives (per conversation).
  const memHydratedRef = useRef(false);

  const loadSuggestions = useCallback(async () => {
    try {
      const goals = await listWorkItems("goal").catch(() => []);
      const allMems = memDataRef.current?.recent ?? [];
      const stale = goals.filter((g) => {
        if (g.status !== "active") return false;
        if (!g.last_activity_at) return true;
        return Date.now() - new Date(g.last_activity_at).getTime() > 3 * 86400000;
      });
      const chips: string[] = [];
      for (const g of stale.slice(0, 2)) {
        chips.push(`目标「${g.title}」已停滞，帮我分析下一步`);
      }
      if (allMems.length > 0) {
        const recent = allMems[0].content.slice(0, 40);
        chips.push(`你之前提到「${recent}${recent.length >= 40 ? "…" : ""}」，继续聊聊？`);
      }
      chips.push("查看今日收件箱摘要");
      chips.push("总结我们最近的对话进展");
      setSuggestions(chips.slice(0, 4));
    } catch {
      setSuggestions(["查看今日收件箱摘要", "帮我规划今天的工作", "总结最近的对话"]);
    }
  }, [conversationId]);

  useEffect(() => {
    // Conversation changed: reload chips. If memories are already cached,
    // mark hydrated so we don't immediately double-fetch.
    memHydratedRef.current = Boolean(memDataRef.current);
    void loadSuggestions();
  }, [loadSuggestions]);

  useEffect(() => {
    if (!memData || memHydratedRef.current) return;
    memHydratedRef.current = true;
    void loadSuggestions();
  }, [memData, loadSuggestions]);

  // Surface a "I just remembered …" toast when the memory cache grows.
  // Uses the TOTAL memory count (not the recent slice length, which is
  // capped at 3 and would silently miss growth from 5 → 6). Suppressed
  // until the user has actually sent a message, so initial mount / route
  // changes / StrictMode double-invoke never fire a spurious toast.
  useEffect(() => {
    if (prevMemoryTotalRef.current === null) {
      prevMemoryTotalRef.current = memoryTotal;
      return;
    }
    if (memoryTotal > prevMemoryTotalRef.current && hasSentRef.current) {
      const newest = recentMemories[0];
      if (newest) {
        setMemoryNotice(
          `我刚记住了：${newest.content.slice(0, 40)}${newest.content.length > 40 ? "…" : ""}`,
        );
        const t = setTimeout(() => setMemoryNotice(null), 6000);
        prevMemoryTotalRef.current = memoryTotal;
        return () => clearTimeout(t);
      }
    }
    prevMemoryTotalRef.current = memoryTotal;
  }, [memoryTotal, recentMemories]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  useEffect(() => {
    if (!isLoading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isLoading]);

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading || pendingConfirmation) return;
    setInput("");
    hasSentRef.current = true;
    // Reset the memory baseline so a memory derived from THIS exchange can
    // still trigger the "I just remembered" toast once.
    prevMemoryTotalRef.current = memData?.memories.length ?? 0;
    await sendMessageBase(
      trimmed,
      (assistantMsgId, event: StreamEvent) => {
        setFromEvent(assistantMsgId, event);
      },
      (error) => {
        addError(error, "对话");
      },
    );
    // No setTimeout here — memory refresh arrives via WS `memory_changed`,
    // which invalidates the TanStack Query cache automatically.
  }, [input, isLoading, pendingConfirmation, sendMessageBase, setFromEvent, addError, memData]);

  const handleConfirm = useCallback(
    async (trustSession?: boolean) => {
      await confirm(setMessages, addError, trustSession);
    },
    [confirm, setMessages, addError],
  );

  const handleDeny = useCallback(async () => {
    await deny(setMessages, addError);
  }, [deny, setMessages, addError]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  // Mark initial load complete once messages are loaded or user sends a message
  useEffect(() => {
    if (messages.length > 0 || pendingConfirmation) {
      setInitialLoad(false);
    }
  }, [messages.length, pendingConfirmation]);

  // Welcome screen when no messages and still in initial load
  if (initialLoad && messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="max-w-lg w-full text-center">
            <div className="text-4xl mb-4">🧠</div>
            <h2 className="text-xl font-semibold text-gray-200 mb-2">开始对话</h2>
            <p className="text-sm text-gray-500 mb-4">
              我是你的个人 AI 助手。所有数据保存在你的机器上，完全私有。
            </p>

            {/* 我记得你 —— 记忆驱动连续性 */}
            {recentMemories.length > 0 && (
              <div className="mb-5 text-left bg-indigo-900/10 border border-indigo-700/30 rounded-xl p-4">
                <div className="flex items-center gap-1.5 mb-2">
                  <span className="text-sm">🧠</span>
                  <span className="text-xs text-indigo-400 font-medium">我记得你</span>
                </div>
                <div className="space-y-1.5">
                  {recentMemories.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => {
                        setInput(
                          `你记得我${m.category === "preference" ? "喜欢" : m.category === "fact" ? "" : "的"}「${m.content.slice(0, 60)}」，基于这个继续聊聊`,
                        );
                        adjustTextareaHeight();
                        setTimeout(() => inputRef.current?.focus(), 0);
                      }}
                      className="block w-full text-left text-xs text-gray-400 hover:text-indigo-300 transition-colors truncate"
                      title={m.content}
                    >
                      · {m.content.slice(0, 60)}
                      {m.content.length > 60 ? "…" : ""}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-wrap justify-center gap-1.5 mb-4">
              {CAPABILITY_CHIPS.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  onClick={() => {
                    setInput(c.prompt);
                    adjustTextareaHeight();
                    setTimeout(() => inputRef.current?.focus(), 0);
                  }}
                  className="flex items-center gap-1 text-xs px-2.5 py-1.5 bg-gray-800/60 hover:bg-gray-700 text-gray-400 hover:text-gray-200 rounded-full border border-gray-700/50 hover:border-emerald-500/30 transition-all"
                  title={c.prompt}
                >
                  <span>{c.icon}</span>
                  <span>{c.label}</span>
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-600 mb-6">点击能力胶囊快速开始，或在下方直接输入</p>
            <div className="flex flex-wrap justify-center gap-2 mb-8">
              {suggestions.map((s) => {
                const SIcon = getSuggestionIcon(s);
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      setInput(s);
                      adjustTextareaHeight();
                      setTimeout(() => inputRef.current?.focus(), 0);
                    }}
                    className="flex items-center gap-1.5 text-xs px-3 py-2 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 rounded-full border border-gray-700 hover:border-emerald-500/30 transition-all"
                  >
                    <SIcon size={13} className="text-emerald-400/70" />
                    <span>{s.length > 50 ? s.slice(0, 50) + "…" : s}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="border-t border-gray-800 p-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex gap-3 items-end bg-gray-900 rounded-xl border border-gray-700 focus-within:border-emerald-600 transition-colors p-3">
              <VoiceInput
                onTranscript={handleVoiceTranscript}
                disabled={isLoading || !!pendingConfirmation}
              />
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onInput={adjustTextareaHeight}
                onKeyDown={handleKeyDown}
                placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                rows={1}
                className="flex-1 bg-transparent border-none outline-none resize-none text-gray-100 placeholder-gray-500 min-h-[24px] max-h-[200px] py-1"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium transition-colors shrink-0"
              >
                发送
              </button>
            </div>
            <p className="text-xs text-gray-600 mt-2 text-center">
              Personal AI Runtime 可能会犯错，请验证重要信息。
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-row min-h-0 relative">
      <div className="flex-1 flex flex-col min-h-0">
        {memoryNotice && (
          <div className="px-4 py-2 bg-indigo-900/20 border-b border-indigo-700/30 flex items-center gap-2 text-xs text-indigo-300 animate-pulse">
            <span>🧠</span>
            <span className="flex-1 truncate">{memoryNotice}</span>
            <button
              onClick={() => setMemoryNotice(null)}
              className="text-indigo-500 hover:text-indigo-300 shrink-0"
            >
              ×
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.map((msg) => (
              <MessageItem key={msg.id} message={msg} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {pendingConfirmation && (
          <div className="border-t border-amber-600/40 px-4 py-3 bg-gray-900/95 backdrop-blur-sm shrink-0">
            <ConfirmationDialog
              toolCall={pendingConfirmation.toolCall}
              onConfirm={handleConfirm}
              onDeny={handleDeny}
            />
          </div>
        )}

        <div className="border-t border-gray-800 p-4">
          <div className="max-w-3xl mx-auto">
            {suggestions.length > 0 && !isLoading && !pendingConfirmation && (
              <div className="flex flex-wrap gap-2 mb-3">
                {suggestions.map((s) => {
                  const SIcon = getSuggestionIcon(s);
                  return (
                    <button
                      key={s}
                      type="button"
                      onClick={() => {
                        setInput(s);
                        adjustTextareaHeight();
                        inputRef.current?.focus();
                      }}
                      className="flex items-center gap-1 text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 rounded-full border border-gray-700 hover:border-emerald-500/30 transition-all"
                    >
                      <SIcon size={12} className="text-emerald-400/70" />
                      <span>{s.length > 50 ? s.slice(0, 50) + "…" : s}</span>
                    </button>
                  );
                })}
              </div>
            )}
            <div className="flex gap-3 items-end bg-gray-900 rounded-xl border border-gray-700 focus-within:border-emerald-600 transition-colors p-3">
              <VoiceInput
                onTranscript={handleVoiceTranscript}
                disabled={isLoading || !!pendingConfirmation}
              />
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onInput={adjustTextareaHeight}
                onKeyDown={handleKeyDown}
                placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                rows={1}
                className="flex-1 bg-transparent border-none outline-none resize-none text-gray-100 placeholder-gray-500 min-h-[24px] max-h-[200px] py-1"
                disabled={isLoading || !!pendingConfirmation}
              />
              <button
                onClick={handleSend}
                disabled={isLoading || !input.trim() || !!pendingConfirmation}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium transition-colors shrink-0"
              >
                {isLoading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                        fill="none"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                      />
                    </svg>
                    思考中
                  </span>
                ) : (
                  "发送"
                )}
              </button>
            </div>
            <p className="text-xs text-gray-600 mt-2 text-center">
              Personal AI Runtime 可能会犯错，请验证重要信息。
            </p>
          </div>
        </div>
      </div>

      <ContextPanel
        lastUserMessage={lastUserMessage}
        toolResults={allToolResults}
        open={contextOpen}
        onToggle={() => setContextOpen(!contextOpen)}
      />
    </div>
  );
}
