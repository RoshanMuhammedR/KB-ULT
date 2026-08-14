"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ConversationSummary } from "@/types/api";
import * as api from "@/lib/api";

type ConversationsValue = {
  conversations: ConversationSummary[];
  loading: boolean;
  refresh: () => Promise<void>;
  rename: (id: string, title: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
};

const ConversationsContext = createContext<ConversationsValue | null>(null);

/** Shared so asking a question on one screen updates the thread list on another. */
export function ConversationsProvider({ children }: { children: React.ReactNode }) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setConversations(await api.listConversations());
    } catch {
      // The list is secondary to the thread you're reading; a failure here stays quiet
      // rather than throwing an error banner over a working conversation.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const rename = useCallback(async (id: string, title: string) => {
    await api.renameConversation(id, title);
    setConversations((current) =>
      current.map((item) => (item.id === id ? { ...item, title } : item))
    );
  }, []);

  const remove = useCallback(async (id: string) => {
    await api.deleteConversation(id);
    setConversations((current) => current.filter((item) => item.id !== id));
  }, []);

  const value = useMemo<ConversationsValue>(
    () => ({ conversations, loading, refresh, rename, remove }),
    [conversations, loading, refresh, rename, remove]
  );

  return (
    <ConversationsContext.Provider value={value}>{children}</ConversationsContext.Provider>
  );
}

export function useConversations(): ConversationsValue {
  const ctx = useContext(ConversationsContext);
  if (!ctx) throw new Error("useConversations must be used within ConversationsProvider");
  return ctx;
}
