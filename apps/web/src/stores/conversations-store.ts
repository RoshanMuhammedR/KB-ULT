"use client";

import { create } from "zustand";
import type { ConversationSummary } from "@/types/api";
import * as api from "@/lib/api";

type ConversationsState = {
  conversations: ConversationSummary[];
  loading: boolean;
  loaded: boolean;
  /** First load. Idempotent, so StrictMode's double mount makes one request, not two. */
  ensureLoaded: () => Promise<void>;
  refresh: () => Promise<void>;
  rename: (id: string, title: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  /** Called when the session ends — the next sign-in must not inherit the old list. */
  reset: () => void;
};

let inFlight: Promise<void> | null = null;

/** Shared so asking a question on one screen updates the thread list on another. */
export const useConversationsStore = create<ConversationsState>()((set, get) => ({
  conversations: [],
  loading: true,
  loaded: false,

  ensureLoaded: () => {
    if (get().loaded) return Promise.resolve();
    // Coalescing on the promise rather than a mount-effect guard covers a second caller from
    // anywhere, not just a second mount.
    inFlight ??= get()
      .refresh()
      .finally(() => {
        inFlight = null;
      });
    return inFlight;
  },

  refresh: async () => {
    try {
      set({ conversations: await api.listConversations(), loaded: true });
    } catch {
      // The list is secondary to the thread you're reading; a failure here stays quiet
      // rather than throwing an error banner over a working conversation.
    } finally {
      set({ loading: false });
    }
  },

  rename: async (id, title) => {
    await api.renameConversation(id, title);
    set((state) => ({
      conversations: state.conversations.map((item) =>
        item.id === id ? { ...item, title } : item
      )
    }));
  },

  remove: async (id) => {
    await api.deleteConversation(id);
    set((state) => ({
      conversations: state.conversations.filter((item) => item.id !== id)
    }));
  },

  reset: () => {
    inFlight = null;
    set({ conversations: [], loading: true, loaded: false });
  }
}));
