/**
 * Conversations list — TanStack Query is the cache source of truth.
 * Optimistic mutations update Query + chatStore together via helpers below,
 * so a later refetch cannot wipe in-flight title/create/delete state with
 * stale server data (we avoid invalidate-after-mutate races).
 */
import { useEffect, useMemo, useRef } from "react";
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { listConversations, ApiError, type Conversation } from "../api/client";
import { useChatStore } from "../stores/chatStore";
import { useErrorStore } from "../stores/errorStore";
import { queryKeys } from "./useWsInvalidationBridge";

function cacheList(qc: QueryClient): Conversation[] {
  return (
    qc.getQueryData<Conversation[]>(queryKeys.conversations) ??
    useChatStore.getState().conversations
  );
}

/** Insert or replace a conversation at the front of the list (store + cache). */
export function upsertConversation(qc: QueryClient, conv: Conversation): void {
  const next = [conv, ...cacheList(qc).filter((c) => c.id !== conv.id)];
  useChatStore.getState().setConversations(next);
  qc.setQueryData(queryKeys.conversations, next);
}

/** Remove a conversation from store + cache (also clears activeId if needed). */
export function removeConversationFromCache(qc: QueryClient, id: string): void {
  useChatStore.getState().removeConversation(id);
  qc.setQueryData<Conversation[]>(queryKeys.conversations, (prev) =>
    (prev ?? []).filter((c) => c.id !== id),
  );
}

/** Patch title in store + cache. */
export function updateConversationTitleInCache(
  qc: QueryClient,
  id: string,
  title: string,
): void {
  useChatStore.getState().updateConversationTitle(id, title);
  qc.setQueryData<Conversation[]>(queryKeys.conversations, (prev) =>
    (prev ?? cacheList(qc)).map((c) => (c.id === id ? { ...c, title } : c)),
  );
}

export function useConversationsQuery() {
  const setConversations = useChatStore((s) => s.setConversations);
  const addError = useErrorStore((s) => s.addError);
  const lastErrorKey = useRef<string | null>(null);

  const query = useQuery<Conversation[]>({
    queryKey: queryKeys.conversations,
    queryFn: listConversations,
    staleTime: 30_000,
    retry: 1,
  });

  // Network/reconcile results → store. Optimistic paths already write both
  // sides with the same list, so this is a no-op for those updates.
  useEffect(() => {
    if (query.data) {
      setConversations(query.data);
      useErrorStore.getState().setBackendUnavailable(false);
    }
  }, [query.data, setConversations]);

  useEffect(() => {
    if (!query.error) {
      lastErrorKey.current = null;
      return;
    }
    const key =
      query.error instanceof ApiError
        ? `${query.error.status}:${query.error.message}`
        : String(query.error);
    if (lastErrorKey.current === key) return;
    lastErrorKey.current = key;

    if (query.error instanceof ApiError && query.error.status === 401) {
      addError("认证失败，请检查 AUTH_TOKEN 与 VITE_AUTH_TOKEN 是否一致", "认证");
    } else {
      useErrorStore.getState().setBackendUnavailable(true);
    }
  }, [query.error, addError]);

  return query;
}

/** Optimistic list mutations that keep Query cache and chatStore aligned. */
export function useConversationCacheActions() {
  const qc = useQueryClient();
  return useMemo(
    () => ({
      upsert: (conv: Conversation) => upsertConversation(qc, conv),
      remove: (id: string) => removeConversationFromCache(qc, id),
      updateTitle: (id: string, title: string) =>
        updateConversationTitleInCache(qc, id, title),
    }),
    [qc],
  );
}

/** Soft refresh from server (e.g. pull-to-refresh). Prefer cache actions after local mutations. */
export function useInvalidateConversations() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.conversations });
  };
}
