import { useState, useCallback, useRef, useEffect } from "react";
import { resolveApproval, ApiError } from "../api/client";
import type { DisplayMessage } from "./useChatMessages";
import { stripToolMarkup } from "../utils/stripToolMarkup";

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

// Session-level trust key for localStorage so trust survives page refresh
const TRUST_KEY_PREFIX = "par_trust_session_";

function _loadTrustedTools(convId: string): Set<string> {
  try {
    const raw = sessionStorage.getItem(TRUST_KEY_PREFIX + convId);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function _saveTrustedTools(convId: string, tools: Set<string>) {
  try {
    sessionStorage.setItem(TRUST_KEY_PREFIX + convId, JSON.stringify([...tools]));
  } catch {
    // sessionStorage may be full or disabled
  }
}

export function useApprovalFlow(conversationId: string) {
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  // 会话级信任缓存：记录当前对话中被信任的工具名（持久化到 sessionStorage）
  const trustedToolsRef = useRef<Set<string>>(_loadTrustedTools(conversationId));
  // 正在处理中的 approval_id 去重集合：防止并发重复提交
  const inflightApprovalsRef = useRef<Set<string>>(new Set());

  // ChatPage 在会话切换时可能复用同一 ChatView 实例；必须按 conversationId 重载信任集，
  // 否则 A 会话「本会话信任」会泄漏到 B，导致误自动批准。
  useEffect(() => {
    trustedToolsRef.current = _loadTrustedTools(conversationId);
    inflightApprovalsRef.current = new Set();
    setPendingConfirmation(null);
  }, [conversationId]);

  const confirm = useCallback(
    async (
      setMessages: React.Dispatch<React.SetStateAction<DisplayMessage[]>>,
      onError?: (msg: string, source: string) => void,
      trustSession?: boolean,
    ) => {
      if (!pendingConfirmation) return;
      const pc = pendingConfirmation;
      setPendingConfirmation(null);

      if (trustSession) {
        trustedToolsRef.current.add(pc.toolCall.function_name);
        _saveTrustedTools(conversationId, trustedToolsRef.current);
      }

      try {
        const res = await resolveApproval(
          pc.approvalId,
          "approve",
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
              content: stripToolMarkup(res.assistant_message),
              isStreaming: false,
            });
          }
          return updated;
        });
      } catch (err) {
        setPendingConfirmation(pc);
        const msg =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "审批操作失败";
        onError?.(msg, "审批");
      }
    },
    [pendingConfirmation, conversationId],
  );

  const deny = useCallback(
    async (
      setMessages: React.Dispatch<React.SetStateAction<DisplayMessage[]>>,
      onError?: (msg: string, source: string) => void,
    ) => {
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
                    content: JSON.stringify({
                      status: "denied",
                      reason: "User denied the operation",
                    }),
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
              content: stripToolMarkup(res.assistant_message),
              isStreaming: false,
            });
          }
          return updated;
        });
      } catch (err) {
        setPendingConfirmation(pc);
        const msg =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "审批操作失败";
        onError?.(msg, "审批");
      }
    },
    [pendingConfirmation, conversationId],
  );

  const setFromEvent = useCallback(
    (
      assistantMsgId: string,
      event: {
        tool_name?: string;
        approval_id?: string;
        tool_args?: Record<string, unknown>;
        tool_call_id?: string;
      },
    ) => {
      const toolName = event.tool_name || "";
      const approvalId = event.approval_id || "";

      // 会话级信任缓存：如果此工具已被信任，自动确认（不弹窗）
      if (toolName && trustedToolsRef.current.has(toolName) && approvalId) {
        // 去重：同一个 approval_id 已在自动处理中，不再重复提交
        if (inflightApprovalsRef.current.has(approvalId)) {
          return;
        }
        inflightApprovalsRef.current.add(approvalId);

        // 触发自动确认
        resolveApproval(
          approvalId,
          "approve",
          toolName,
          event.tool_args || {},
          conversationId,
          event.tool_call_id || "",
        )
          .catch(() => {
            // 自动确认失败则回退到手动（仅当 409 冲突时 backend 已拒绝，不再弹窗）
          })
          .finally(() => {
            inflightApprovalsRef.current.delete(approvalId);
          });
        return;
      }

      setPendingConfirmation({
        toolCall: {
          index: 0,
          id: event.tool_call_id || "",
          function_name: toolName,
          arguments: JSON.stringify(event.tool_args || {}),
        },
        approvalId: approvalId,
        assistantMsgId,
      });
    },
    [conversationId],
  );

  return { pendingConfirmation, setPendingConfirmation, setFromEvent, confirm, deny };
}
