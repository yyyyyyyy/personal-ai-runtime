import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { getMessages, sendMessage, updateConversation, ApiError } from "../api/client";
import type { Message, StreamEvent, SourceCitation } from "../api/client";
import { useChatStore } from "../stores/chatStore";
import { stripToolMarkup } from "../utils/stripToolMarkup";

interface ToolResult {
  tool_name: string;
  tool_call_id: string;
  content: string;
}

export interface DisplayMessage {
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
  sources?: SourceCitation[];
}

function parseToolCalls(raw: string): DisplayMessage["toolCalls"] {
  const parsed = JSON.parse(raw);
  const list = Array.isArray(parsed) ? parsed : [];
  return list.map(
    (
      tc: {
        index?: number;
        id?: string;
        function?: { name?: string; arguments?: string | Record<string, unknown> };
        function_name?: string;
        arguments?: string | Record<string, unknown>;
      },
      idx: number,
    ) => ({
      index: tc.index ?? idx,
      id: tc.id ?? "",
      function_name: tc.function?.name ?? tc.function_name ?? "",
      arguments:
        typeof tc.function?.arguments === "string"
          ? tc.function.arguments
          : JSON.stringify(tc.function?.arguments ?? tc.arguments ?? {}),
    }),
  );
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
      content: m.role === "assistant" ? stripToolMarkup(m.content ?? "") : (m.content ?? ""),
      expandTools: true,
    };

    // Parse persisted sources for "I Remember" markers
    if (m.role === "assistant" && m.sources) {
      try {
        display.sources = typeof m.sources === "string" ? JSON.parse(m.sources) : m.sources;
      } catch {
        // ignore parse errors
      }
    }

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
              : (inboxSummaryFromResults(matched) ?? "");
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

export function useChatMessages(
  conversationId: string,
  onLoadError?: (msg: string, source: string) => void,
) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");

  const conversations = useChatStore((s) => s.conversations);
  const updateConversationTitle = useChatStore((s) => s.updateConversationTitle);

  const onLoadErrorRef = useRef(onLoadError);
  onLoadErrorRef.current = onLoadError;

  const lastUserMessage = useMemo(() => {
    const userMsgs = messages.filter((m) => m.role === "user");
    return userMsgs.length > 0 ? userMsgs[userMsgs.length - 1].content : undefined;
  }, [messages]);

  const allToolResults = useMemo(() => messages.flatMap((m) => m.toolResults || []), [messages]);

  const loadMessages = useCallback(async () => {
    try {
      const msgs = await getMessages(conversationId);
      setMessages(parseLoadedMessages(msgs));
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "加载消息失败";
      onLoadErrorRef.current?.(msg, "对话");
    }
    setStreamingContent("");
  }, [conversationId]);

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  const handleSend = useCallback(
    async (
      text: string,
      onConfirmationRequired?: (assistantMsgId: string, event: StreamEvent) => void,
      onError?: (msg: string) => void,
    ) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;

      const userMsg: DisplayMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: trimmed,
      };

      const conv = conversations.find((c) => c.id === conversationId);
      const isFirstUserMessage = messages.filter((m) => m.role === "user").length === 0;
      const isDefaultTitle =
        !conv?.title ||
        conv.title === "New Conversation" ||
        conv.title === "New Chat" ||
        conv.title === "新对话";
      const needsTitle = isFirstUserMessage && isDefaultTitle;

      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setStreamingContent("");

      if (needsTitle) {
        const title =
          trimmed.length > 25 ? `讨论「${trimmed.slice(0, 25)}…」` : `讨论「${trimmed}」`;
        updateConversation(conversationId, title)
          .then(() => updateConversationTitle(conversationId, title))
          .catch(() => {
            onLoadErrorRef.current?.("更新对话标题失败", "对话");
          });
      }

      let tempContent = "";
      let tempToolCalls: DisplayMessage["toolCalls"] = [];
      let tempToolResults: DisplayMessage["toolResults"] = [];
      let tempSources: SourceCitation[] = [];
      let awaitingApproval = false;

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
          const displayContent = stripToolMarkup(tempContent, { trim: false });
          setStreamingContent(displayContent);
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantMsg.id ? { ...m, content: displayContent } : m)),
          );
        } else if (event.type === "tool_call_start" && event.tool_calls) {
          tempToolCalls = event.tool_calls;
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantMsg.id ? { ...m, toolCalls: tempToolCalls } : m)),
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
                : m,
            ),
          );
        } else if (event.type === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: tempContent + `\n\n⚠️ ${event.content}`, isStreaming: false }
                : m,
            ),
          );
        } else if (event.type === "done") {
          const finalContent = awaitingApproval
            ? stripToolMarkup(tempContent)
            : stripToolMarkup(tempContent) || "抱歉，未能生成回复，请再试一次。";
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, isStreaming: false, content: finalContent } : m,
            ),
          );
          setStreamingContent("");
        } else if (event.type === "sources" && event.sources) {
          tempSources = event.sources;
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantMsg.id ? { ...m, sources: tempSources } : m)),
          );
        } else if (event.type === "confirmation_required" && event.tool_name && event.approval_id) {
          awaitingApproval = true;
          onConfirmationRequired?.(assistantMsg.id, event);
        }
      };

      try {
        await sendMessage(
          conversationId,
          trimmed,
          handleEvent,
          (error) => {
            setIsLoading(false);
            onError?.(error);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? { ...m, content: `错误：${error}`, isStreaming: false }
                  : m,
              ),
            );
          },
          () => {
            setIsLoading(false);
          },
        );
      } catch (err: unknown) {
        setIsLoading(false);
        const errorMsg =
          err instanceof ApiError ? err.message : err instanceof Error ? err.message : "未知错误";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, content: `错误：${errorMsg}`, isStreaming: false }
              : m,
          ),
        );
      }
    },
    [isLoading, conversationId, conversations, messages, updateConversationTitle],
  );

  return {
    messages,
    setMessages,
    isLoading,
    streamingContent,
    setStreamingContent,
    loadMessages,
    handleSend,
    lastUserMessage,
    allToolResults,
  };
}
