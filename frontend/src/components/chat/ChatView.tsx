import { useState, useEffect, useRef, useCallback } from "react";
import { getMessages, sendMessage, resolveApproval } from "../../api/client";
import type { Message, StreamEvent } from "../../api/client";
import MessageItem from "./MessageItem";
import ConfirmationDialog from "./ConfirmationDialog";

interface Props {
  conversationId: string;
}

interface ToolResult {
  tool_name: string;
  tool_call_id: string;
  content: string;
}

interface PendingConfirmation {
  toolCall: {
    index: number;
    id: string;
    function_name: string;
    arguments: string;
  };
  approvalId: string;
  assistantMsgId: string;
}

interface DisplayMessage {
  id: string;
  role: string;
  content: string;
  isStreaming?: boolean;
  expandTools?: boolean;
  toolCalls?: Array<{
    index: number;
    id: string;
    function_name: string;
    arguments: string;
  }>;
  toolResults?: ToolResult[];
}

function parseToolCalls(raw: string): DisplayMessage["toolCalls"] {
  const parsed = JSON.parse(raw);
  const list = Array.isArray(parsed) ? parsed : [];
  return list.map((tc: any, idx: number) => ({
    index: tc.index ?? idx,
    id: tc.id ?? "",
    function_name: tc.function?.name ?? tc.function_name ?? "",
    arguments:
      typeof tc.function?.arguments === "string"
        ? tc.function.arguments
        : JSON.stringify(tc.function?.arguments ?? tc.arguments ?? {}),
  }));
}

function inboxSummaryFromResults(results: ToolResult[]): string | null {
  for (const r of results) {
    if (r.tool_name !== "check_inbox") continue;
    try {
      const data = JSON.parse(r.content);
      if (data.emails && !data.error) {
        return `📧 已读取 ${data.count ?? data.emails.length} 封邮件`;
      }
    } catch {
      // ignore
    }
  }
  return null;
}

/** Parse loaded messages, pairing assistant tool_calls with subsequent tool result messages. */
function parseLoadedMessages(msgs: Message[]): DisplayMessage[] {
  const toolResults: Record<string, ToolResult> = {};
  for (const m of msgs) {
    if (m.role === "tool" && m.tool_call_id) {
      toolResults[m.tool_call_id] = {
        tool_name: "",
        tool_call_id: m.tool_call_id,
        content: m.content ?? "",
      };
    }
  }

  const result: DisplayMessage[] = [];
  for (const m of msgs) {
    if (m.role === "tool") continue;

    const display: DisplayMessage = {
      id: m.id,
      role: m.role,
      content: m.content ?? "",
      expandTools: true,
    };

    if (m.tool_calls) {
      try {
        display.toolCalls = parseToolCalls(m.tool_calls);
        const tcs = display.toolCalls!;
        const matched: ToolResult[] = [];
        for (const tc of tcs) {
          const tr = toolResults[tc.id];
          if (tr) {
            matched.push({ ...tr, tool_name: tc.function_name });
          }
        }
        if (matched.length > 0) {
          display.toolResults = matched;
        }

        const hasInbox = matched.some((r) => r.tool_name === "check_inbox");
        const hasText = Boolean(display.content?.trim());
        if (hasInbox && matched.length > 0) {
          // UI already shows the inbox table — avoid duplicating a long LLM summary
          const count = (() => {
            try {
              const r = matched.find((x) => x.tool_name === "check_inbox");
              if (!r) return 0;
              const data = JSON.parse(r.content);
              return data.count ?? data.emails?.length ?? 0;
            } catch {
              return 0;
            }
          })();
          display.content =
            count > 0
              ? `已加载最近 ${count} 封邮件，详见上方列表。需要我帮您查看某封详情或处理待办吗？`
              : inboxSummaryFromResults(matched) ?? "";
        } else if (!hasText && matched.length > 0) {
          const summary = inboxSummaryFromResults(matched);
          display.content = summary ?? "";
        } else if (!hasText && tcs.length > 0 && matched.length === 0) {
          display.content = `[调用工具: ${tcs.map((tc) => tc.function_name).join(", ")}]`;
        }
      } catch {
        // ignore parse errors
      }
    }

    result.push(display);
  }

  return result;
}

export default function ChatView({ conversationId }: Props) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    loadMessages();
  }, [conversationId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent]);

  useEffect(() => {
    if (!isLoading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isLoading]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const loadMessages = async () => {
    try {
      const msgs = await getMessages(conversationId);
      setMessages(parseLoadedMessages(msgs));
    } catch {
      // Backend may not be running
    }
    setStreamingContent("");
  };

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMsg: DisplayMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);
    setStreamingContent("");

    let tempContent = "";
    let tempToolCalls: DisplayMessage["toolCalls"] = [];
    let tempToolResults: DisplayMessage["toolResults"] = [];

    const assistantMsg: DisplayMessage = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      isStreaming: true,
    };

    setMessages((prev) => [...prev, assistantMsg]);

    const handleEvent = (event: StreamEvent) => {
      if (event.type === "text_delta" && event.content) {
        tempContent += event.content;
        setStreamingContent(tempContent);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id ? { ...m, content: tempContent } : m
          )
        );
      } else if (event.type === "tool_call_start" && event.tool_calls) {
        tempToolCalls = event.tool_calls;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id ? { ...m, toolCalls: tempToolCalls } : m
          )
        );
      } else if (event.type === "tool_result") {
        tempToolResults = [
          ...(tempToolResults || []),
          {
            tool_name: event.tool_name || "unknown",
            tool_call_id: event.tool_call_id || "",
            content: event.content || "",
          },
        ];
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, toolResults: tempToolResults, expandTools: true }
              : m
          )
        );
      } else if (event.type === "error") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, content: tempContent + `\n\n⚠️ ${event.content}`, isStreaming: false }
              : m
          )
        );
      } else if (event.type === "done") {
        const finalContent =
          tempContent.trim() || "抱歉，未能生成回复，请再试一次。";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, isStreaming: false, content: finalContent }
              : m
          )
        );
        setStreamingContent("");
      } else if (event.type === "confirmation_required" && event.tool_name && event.approval_id) {
        // Show confirmation dialog and pause
        setPendingConfirmation({
          toolCall: {
            index: 0,
            id: event.tool_call_id || "",
            function_name: event.tool_name,
            arguments: JSON.stringify(event.tool_args || {}),
          },
          approvalId: event.approval_id,
          assistantMsgId: assistantMsg.id,
        });
      }
    };

    try {
      await sendMessage(
        conversationId,
        trimmed,
        handleEvent,
        (error) => {
          setIsLoading(false);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: `Error: ${error}`, isStreaming: false }
                : m
            )
          );
        },
        () => {
          setIsLoading(false);
        }
      );
    } catch (err: unknown) {
      setIsLoading(false);
      const errorMsg = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id
            ? { ...m, content: `Error: ${errorMsg}`, isStreaming: false }
            : m
        )
      );
    }
  }, [input, isLoading, conversationId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleConfirm = async () => {
    if (!pendingConfirmation) return;
    const pc = pendingConfirmation;
    setPendingConfirmation(null);

    try {
      const res = await resolveApproval(
        pc.approvalId,
        "approve",
        pc.toolCall.function_name,
        JSON.parse(pc.toolCall.arguments || "{}"),
        conversationId,
        pc.toolCall.id,
      );
      // Append the resolved tool result and follow-up assistant reply
      setMessages((prev) => {
        const updated = prev.map((m) => {
          if (m.id === pc.assistantMsgId) {
            const existing = m.toolResults || [];
            return {
              ...m,
              isStreaming: false,
              toolResults: res.result
                ? [
                    ...existing,
                    {
                      tool_name: pc.toolCall.function_name,
                      tool_call_id: pc.toolCall.id,
                      content: res.result,
                    },
                  ]
                : existing,
            };
          }
          return m;
        });
        if (res.assistant_message) {
          updated.push({
            id: `assistant-followup-${Date.now()}`,
            role: "assistant",
            content: res.assistant_message,
            isStreaming: false,
          });
        }
        return updated;
      });
    } catch {
      // Error handled silently
    }
  };

  const handleDeny = async () => {
    if (!pendingConfirmation) return;
    const pc = pendingConfirmation;
    setPendingConfirmation(null);

    try {
      const res = await resolveApproval(
        pc.approvalId,
        "deny",
        pc.toolCall.function_name,
        JSON.parse(pc.toolCall.arguments || "{}"),
        conversationId,
        pc.toolCall.id,
      );
      setMessages((prev) => {
        const updated = prev.map((m) => {
          if (m.id === pc.assistantMsgId) {
            const existing = m.toolResults || [];
            return {
              ...m,
              isStreaming: false,
              toolResults: [
                ...existing,
                {
                  tool_name: pc.toolCall.function_name,
                  tool_call_id: pc.toolCall.id,
                  content: JSON.stringify({ status: "denied", reason: "User denied the operation" }),
                },
              ],
            };
          }
          return m;
        });
        if (res.assistant_message) {
          updated.push({
            id: `assistant-followup-${Date.now()}`,
            role: "assistant",
            content: res.assistant_message,
            isStreaming: false,
          });
        }
        return updated;
      });
    } catch {
      // Error handled silently
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-3xl mx-auto space-y-4">
          {pendingConfirmation && (
            <ConfirmationDialog
              toolCall={pendingConfirmation.toolCall}
              onConfirm={handleConfirm}
              onDeny={handleDeny}
            />
          )}
          {messages.map((msg) => (
            <MessageItem key={msg.id} message={msg} />
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      <div className="border-t border-gray-800 p-4">
        <div className="max-w-3xl mx-auto">
          <div className="flex gap-3 items-end bg-gray-900 rounded-xl border border-gray-700 focus-within:border-emerald-600 transition-colors p-3">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              rows={1}
              className="flex-1 bg-transparent border-none outline-none resize-none text-gray-100 placeholder-gray-500 min-h-[24px] max-h-[200px] py-1"
              disabled={isLoading}
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
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
  );
}
