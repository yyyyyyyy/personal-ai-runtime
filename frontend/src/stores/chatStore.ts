import { create } from "zustand";
import type { Conversation } from "../api/client";

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  pendingPrompt: string | null;
  loading: boolean;

  setConversations: (convs: Conversation[]) => void;
  setActiveConversation: (id: string | null) => void;
  addConversation: (conv: Conversation) => void;
  removeConversation: (id: string) => void;
  updateConversationTitle: (id: string, title: string) => void;
  setPendingPrompt: (prompt: string | null) => void;
  setLoading: (loading: boolean) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  activeConversationId: null,
  pendingPrompt: null,
  loading: false,

  setConversations: (convs) => set({ conversations: convs }),
  setActiveConversation: (id) => set({ activeConversationId: id }),
  addConversation: (conv) =>
    set((state) => ({ conversations: [conv, ...state.conversations] })),
  removeConversation: (id) =>
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      activeConversationId:
        state.activeConversationId === id ? null : state.activeConversationId,
    })),
  updateConversationTitle: (id, title) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, title } : c
      ),
    })),
  setPendingPrompt: (prompt) => set({ pendingPrompt: prompt }),
  setLoading: (loading) => set({ loading }),
}));
