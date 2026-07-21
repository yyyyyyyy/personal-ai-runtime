import { useNavigate } from "react-router-dom";
import { createConversation, ApiError } from "../api/client";
import { useChatStore } from "../stores/chatStore";
import { useErrorStore } from "../stores/errorStore";
import { useConversationCacheActions } from "./useConversationsQuery";

interface QuickChatOptions {
  title?: string;
  prompt?: string;
  fallbackError?: string;
}

/** Creates a conversation and navigates to it, optionally setting a pending prompt. */
export function useQuickChat() {
  const navigate = useNavigate();
  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const setPendingPrompt = useChatStore((s) => s.setPendingPrompt);
  const addError = useErrorStore((s) => s.addError);
  const { upsert } = useConversationCacheActions();

  return async (opts: QuickChatOptions = {}) => {
    const { title, prompt, fallbackError = "创建对话失败" } = opts;
    try {
      const conv = await createConversation(title);
      upsert(conv);
      setActiveConversation(conv.id);
      if (prompt) setPendingPrompt(prompt);
      navigate(`/chat/${conv.id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : fallbackError;
      addError(msg, "对话");
    }
  };
}
