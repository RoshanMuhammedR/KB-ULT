"use client";

import { create } from "zustand";
import type { WorkspaceMemory } from "@/types/api";
import * as api from "@/lib/api";

type MemoriesState = {
  memories: WorkspaceMemory[];
  /**
   * Whether memory actually reaches an answer. `null` until asked.
   *
   * Kept beside the list because the two say different things: an empty list means "nothing
   * learned yet", and `enabled: false` means "nothing here will ever be used". Showing the
   * first when the truth is the second is the bug this whole page had.
   */
  enabled: boolean | null;
  loading: boolean;
  loaded: boolean;
  /** First load. Idempotent, so StrictMode's double mount makes one request, not two. */
  ensureLoaded: () => Promise<void>;
  refresh: () => Promise<void>;
  add: (content: string) => Promise<void>;
  edit: (id: string, content: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  forgetAll: () => Promise<void>;
  /** Called when the session ends — the next sign-in must not inherit the old list. */
  reset: () => void;
};

let inFlight: Promise<void> | null = null;

export const useMemoriesStore = create<MemoriesState>()((set, get) => ({
  memories: [],
  enabled: null,
  loading: true,
  loaded: false,

  ensureLoaded: () => {
    if (get().loaded) return Promise.resolve();
    inFlight ??= get()
      .refresh()
      .finally(() => {
        inFlight = null;
      });
    return inFlight;
  },

  refresh: async () => {
    try {
      const [status, memories] = await Promise.all([
        api.getMemoryStatus(),
        api.listMemories()
      ]);
      set({ memories, enabled: status.enabled, loaded: true });
    } catch {
      // Quiet, like the conversations store: a memory list that fails to load should not
      // throw a banner over the page the user actually came to read.
    } finally {
      set({ loading: false });
    }
  },

  add: async (content) => {
    const memory = await api.createMemory(content);
    set((state) => ({ memories: [memory, ...state.memories] }));
  },

  edit: async (id, content) => {
    const memory = await api.updateMemory(id, content);
    set((state) => ({
      memories: state.memories.map((item) => (item.id === id ? memory : item))
    }));
  },

  remove: async (id) => {
    await api.deleteMemory(id);
    set((state) => ({ memories: state.memories.filter((item) => item.id !== id) }));
  },

  forgetAll: async () => {
    await api.forgetAllMemories();
    set({ memories: [] });
  },

  reset: () => {
    inFlight = null;
    set({ memories: [], enabled: null, loading: true, loaded: false });
  }
}));
