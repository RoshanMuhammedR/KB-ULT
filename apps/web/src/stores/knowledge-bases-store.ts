"use client";

import { create } from "zustand";
import type { KnowledgeBase } from "@/types/api";
import * as api from "@/lib/api";

/**
 * Which library you are looking at, and which libraries the chat is answering from.
 *
 * Two separate ideas, deliberately. `selectedId` scopes what the Library and the thread list
 * show — one place at a time, like a folder. `attachedIds` is what a question is answered
 * from, and can be several at once, because "attach a base and chat with it" is the shape
 * this was asked for. Collapsing them into one selection would make it impossible to read
 * across two libraries without also splitting your sources view in half.
 */
const SELECTED_KEY = "saga.kb.selected";
const ATTACHED_KEY = "saga.kb.attached";

type KnowledgeBasesState = {
  bases: KnowledgeBase[];
  selectedId: string | null;
  attachedIds: string[];
  loading: boolean;
  loaded: boolean;
  ensureLoaded: () => Promise<void>;
  refresh: () => Promise<void>;
  select: (id: string) => void;
  setAttached: (ids: string[]) => void;
  toggleAttached: (id: string) => void;
  add: (name: string) => Promise<KnowledgeBase>;
  rename: (id: string, name: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  reset: () => void;
};

let inFlight: Promise<void> | null = null;

/** Survives a reload so a switcher does not reset itself every time the tab is opened. */
function remember(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Private windows and blocked site data both throw here. A forgotten selection is a
    // smaller problem than a page that will not render.
  }
}

function recall(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export const useKnowledgeBasesStore = create<KnowledgeBasesState>()((set, get) => ({
  bases: [],
  selectedId: null,
  attachedIds: [],
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
      const bases = await api.listKnowledgeBases();
      const known = new Set(bases.map((base) => base.id));

      // A remembered id that no longer exists — someone deleted the base, possibly in
      // another tab — must not leave the app pointing at nothing.
      const storedSelected = recall(SELECTED_KEY);
      const selectedId =
        storedSelected && known.has(storedSelected) ? storedSelected : bases[0]?.id ?? null;

      const storedAttached = (recall(ATTACHED_KEY) ?? "")
        .split(",")
        .filter((id) => id && known.has(id));
      const attachedIds = storedAttached.length ? storedAttached : selectedId ? [selectedId] : [];

      set({ bases, selectedId, attachedIds, loaded: true });
    } catch {
      // Quiet, like the other stores: a switcher that fails to load should not throw a
      // banner over the page the user came to read.
    } finally {
      set({ loading: false });
    }
  },

  select: (id) => {
    remember(SELECTED_KEY, id);
    // Selecting a library also attaches it, because that is what someone means by clicking
    // it. Anything else already attached stays — de-selecting is an explicit act.
    const attachedIds = get().attachedIds.includes(id) ? get().attachedIds : [...get().attachedIds, id];
    remember(ATTACHED_KEY, attachedIds.join(","));
    set({ selectedId: id, attachedIds });
  },

  setAttached: (ids) => {
    remember(ATTACHED_KEY, ids.join(","));
    set({ attachedIds: ids });
  },

  toggleAttached: (id) => {
    const current = get().attachedIds;
    const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id];
    // Never leave the chat with nothing to answer from: unticking the last base would make
    // every question fall back to the workspace default without saying so.
    const settled = next.length ? next : current;
    remember(ATTACHED_KEY, settled.join(","));
    set({ attachedIds: settled });
  },

  add: async (name) => {
    const base = await api.createKnowledgeBase(name);
    set((state) => ({ bases: [...state.bases, base] }));
    get().select(base.id);
    return base;
  },

  rename: async (id, name) => {
    const base = await api.renameKnowledgeBase(id, name);
    set((state) => ({ bases: state.bases.map((item) => (item.id === id ? base : item)) }));
  },

  remove: async (id) => {
    await api.deleteKnowledgeBase(id);
    const bases = get().bases.filter((base) => base.id !== id);
    const attachedIds = get().attachedIds.filter((item) => item !== id);
    const selectedId = get().selectedId === id ? bases[0]?.id ?? null : get().selectedId;
    remember(ATTACHED_KEY, attachedIds.join(","));
    if (selectedId) remember(SELECTED_KEY, selectedId);
    set({
      bases,
      selectedId,
      attachedIds: attachedIds.length ? attachedIds : selectedId ? [selectedId] : []
    });
  },

  reset: () => {
    inFlight = null;
    set({ bases: [], selectedId: null, attachedIds: [], loading: true, loaded: false });
  }
}));
