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

type SetMessages = React.Dispatch<React.SetStateAction<DisplayMessage[]>>;

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

function applyResolveToMessages(
  setMessages: SetMessages,
  assistantMsgId: string,
  toolName: string,
  toolCallId: string,
  res: { result?: string; assistant_message?: string },
  options?: { denied?: boolean },
) {
  setMessages((prev) => {
    const updated = prev.map((m) => {
      if (m.id !== assistantMsgId) return m;
      const existing = m.toolResults || [];
      const content = options?.denied
        ? JSON.stringify({ status: "denied", reason: "User denied the operation" })
        : res.result;
      return {
        ...m,
        isStreaming: false,
        toolResults: content
          ? [...existing, { tool_name: toolName, tool_call_id: toolCallId, content }]
          : existing,
      };
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
}

export function useApprovalFlow(conversationId: string) {
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const trustedToolsRef = useRef<Set<string>>(_loadTrustedTools(conversationId));
  const inflightApprovalsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    trustedToolsRef.current = _loadTrustedTools(conversationId);
    inflightApprovalsRef.current = new Set();
    setPendingConfirmation(null);
  }, [conversationId]);

  const confirm = useCallback(
    async (
      setMessages: SetMessages,
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
        applyResolveToMessages(
          setMessages,
          pc.assistantMsgId,
          pc.toolCall.function_name,
          pc.toolCall.id,
          res,
        );
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
      setMessages: SetMessages,
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
        applyResolveToMessages(
          setMessages,
          pc.assistantMsgId,
          pc.toolCall.function_name,
          pc.toolCall.id,
          res,
          { denied: true },
        );
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
      setMessages?: SetMessages,
    ) => {
      const toolName = event.tool_name || "";
      const approvalId = event.approval_id || "";
      const toolCallId = event.tool_call_id || "";

      // 会话级信任：自动批准并写回 tool result + 续写（P3）
      if (toolName && trustedToolsRef.current.has(toolName) && approvalId) {
        if (inflightApprovalsRef.current.has(approvalId)) {
          return;
        }
        inflightApprovalsRef.current.add(approvalId);

        resolveApproval(
          approvalId,
          "approve",
          toolName,
          event.tool_args || {},
          conversationId,
          toolCallId,
        )
          .then((res) => {
            if (setMessages) {
              applyResolveToMessages(
                setMessages,
                assistantMsgId,
                toolName,
                toolCallId,
                res,
              );
            }
          })
          .catch((err) => {
            // 409 = approval already resolved elsewhere (e.g. Approvals page
            // or a duplicate event). Backend has already acted, so silence
            // rather than surface a stale confirmation dialog the user
            // cannot usefully act on. Other errors fall back to manual.
            const status = err instanceof ApiError ? err.status : 0;
            if (status === 409) {
              return;
            }
            setPendingConfirmation({
              toolCall: {
                index: 0,
                id: toolCallId,
                function_name: toolName,
                arguments: JSON.stringify(event.tool_args || {}),
              },
              approvalId,
              assistantMsgId,
            });
          })
          .finally(() => {
            inflightApprovalsRef.current.delete(approvalId);
          });
        return;
      }

      setPendingConfirmation({
        toolCall: {
          index: 0,
          id: toolCallId,
          function_name: toolName,
          arguments: JSON.stringify(event.tool_args || {}),
        },
        approvalId,
        assistantMsgId,
      });
    },
    [conversationId],
  );

  return { pendingConfirmation, setPendingConfirmation, setFromEvent, confirm, deny };
}
