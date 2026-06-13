import { useState, useCallback } from "react";
import { resolveApproval, ApiError } from "../api/client";
import type { DisplayMessage } from "./useChatMessages";

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

export function useApprovalFlow(conversationId: string) {
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  const confirm = useCallback(
    async (
      setMessages: React.Dispatch<React.SetStateAction<DisplayMessage[]>>,
      onError?: (msg: string, source: string) => void
    ) => {
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
    [pendingConfirmation, conversationId]
  );

  const deny = useCallback(
    async (
      setMessages: React.Dispatch<React.SetStateAction<DisplayMessage[]>>,
      onError?: (msg: string, source: string) => void
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
    [pendingConfirmation, conversationId]
  );

  const setFromEvent = useCallback(
    (assistantMsgId: string, event: { tool_name?: string; approval_id?: string; tool_args?: Record<string, unknown>; tool_call_id?: string }) => {
      setPendingConfirmation({
        toolCall: {
          index: 0,
          id: event.tool_call_id || "",
          function_name: event.tool_name || "",
          arguments: JSON.stringify(event.tool_args || {}),
        },
        approvalId: event.approval_id || "",
        assistantMsgId,
      });
    },
    []
  );

  return { pendingConfirmation, setPendingConfirmation, setFromEvent, confirm, deny };
}
