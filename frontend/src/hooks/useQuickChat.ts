import { useNavigate } from "react-router-dom";
import { createConversation, ApiError } from "../api/client";
import { useChatStore } from "../stores/chatStore";
import { useErrorStore } from "../stores/errorStore";

interface QuickChatOptions {
  title?: string;
  prompt?: string;
  fallbackError?: string;
}

/** Creates a conversation and navigates to it, optionally setting a pending prompt. */
export function useQuickChat() {
  const navigate = useNavigate();
  const addConversation = useChatStore((s) => s.addConversation);
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const setPendingPrompt = useChatStore((s) => s.setPendingPrompt);
  const addError = useErrorStore((s) => s.addError);

  return async (opts: QuickChatOptions = {}) => {
    const { title, prompt, fallbackError = "创建对话失败" } = opts;
    try {
      const conv = await createConversation(title);
      addConversation(conv);
      setActiveConversation(conv.id);
      if (prompt) setPendingPrompt(prompt);
      navigate(`/chat/${conv.id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : fallbackError;
      addError(msg, "对话");
    }
  };
}
