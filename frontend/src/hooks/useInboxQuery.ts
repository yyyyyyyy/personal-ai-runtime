/**
 * Inbox emails + digest. Poll/status mutations invalidate queryKeys.inbox.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listInboxEmails, getInboxDigest, type InboxEmail } from "../api/client";
import { queryKeys } from "./useWsInvalidationBridge";

export interface InboxData {
  emails: InboxEmail[];
  digest: { title?: string; content?: string; message?: string };
}

export function useInboxQuery(enabled = true) {
  return useQuery<InboxData>({
    queryKey: queryKeys.inbox,
    queryFn: async () => {
      const [emails, digest] = await Promise.all([
        listInboxEmails(undefined, "pending"),
        getInboxDigest(),
      ]);
      return { emails, digest };
    },
    enabled,
    staleTime: 30_000,
  });
}

export function useInvalidateInbox() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.inbox });
  };
}
