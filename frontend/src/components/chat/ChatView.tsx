import { useState, useEffect, useRef, useCallback } from "react";
import { listGoals, ApiError } from "../../api/client";
import { type StreamEvent } from "../../api/client";
import { useErrorStore } from "../../stores/errorStore";
import { useChatStore } from "../../stores/chatStore";
import { useChatMessages } from "../../hooks/useChatMessages";
import { useApprovalFlow } from "../../hooks/useApprovalFlow";
import MessageItem from "./MessageItem";
import ConfirmationDialog from "./ConfirmationDialog";
import ContextPanel from "./ContextPanel";

interface Props {
  conversationId: string;
}

export default function ChatView({ conversationId }: Props) {
  const [input, setInput] = useState("");
  const [contextOpen, setContextOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const addError = useErrorStore((s) => s.addError);
  const pendingPrompt = useChatStore((s) => s.pendingPrompt);
  const setPendingPrompt = useChatStore((s) => s.setPendingPrompt);

  const {
    messages,
    setMessages,
    isLoading,
    streamingContent,
    loadMessages,
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

  useEffect(() => {
    loadSuggestions();
  }, [conversationId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  useEffect(() => {
    if (!isLoading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isLoading]);

  const loadSuggestions = async () => {
    try {
      const goals = await listGoals();
      const stagnant = goals.filter((g) => {
        if (g.status !== "active") return false;
        if (!g.last_activity_at) return true;
        return Date.now() - new Date(g.last_activity_at).getTime() > 3 * 86400000;
      });
      const chips: string[] = [];
      for (const g of stagnant.slice(0, 2)) {
        chips.push(`目标「${g.title}」已停滞，帮我分析下一步`);
      }
      chips.push("查看今日收件箱摘要");
      chips.push("总结我们最近的对话进展");
      setSuggestions(chips.slice(0, 3));
    } catch {
      setSuggestions(["查看今日收件箱摘要", "帮我规划今天的工作"]);
    }
  };

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading || pendingConfirmation) return;
    setInput("");
    await sendMessageBase(trimmed, (assistantMsgId, event: StreamEvent) => {
      setFromEvent(assistantMsgId, event);
    }, (error) => {
      addError(error, "对话");
    });
  }, [input, isLoading, pendingConfirmation, sendMessageBase, setFromEvent, addError]);

  const handleConfirm = useCallback(async () => {
    await confirm(setMessages, addError);
  }, [confirm, setMessages, addError]);

  const handleDeny = useCallback(async () => {
    await deny(setMessages, addError);
  }, [deny, setMessages, addError]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex-1 flex flex-row min-h-0 relative">
      <div className="flex-1 flex flex-col min-h-0">
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
                {suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      setInput(s);
                      adjustTextareaHeight();
                      inputRef.current?.focus();
                    }}
                    className="text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 rounded-full border border-gray-700 transition-colors"
                  >
                    {s.length > 40 ? s.slice(0, 40) + "…" : s}
                  </button>
                ))}
              </div>
            )}
            <div className="flex gap-3 items-end bg-gray-900 rounded-xl border border-gray-700 focus-within:border-emerald-600 transition-colors p-3">
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
                        cx="12" cy="12" r="10"
                        stroke="currentColor" strokeWidth="4" fill="none"
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
