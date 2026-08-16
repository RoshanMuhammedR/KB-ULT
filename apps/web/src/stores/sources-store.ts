"use client";

import { create } from "zustand";
import { countByState, sourceTitle } from "@kb/shared";
import type { KnowledgeAsset } from "@/types/api";
import * as api from "@/lib/api";
import { follow, followAll, stopAll, unfollow } from "@/lib/ingestion-poller";
import { toast } from "@/stores/toast-store";

type Counts = ReturnType<typeof countByState>;

const EMPTY_COUNTS: Counts = { total: 0, ready: 0, processing: 0, failed: 0 };

function sameCounts(a: Counts, b: Counts): boolean {
  return (
    a.total === b.total &&
    a.ready === b.ready &&
    a.processing === b.processing &&
    a.failed === b.failed
  );
}

type SourcesState = {
  sources: KnowledgeAsset[];
  counts: Counts;
  loading: boolean;
  loaded: boolean;
  /** First load. Idempotent, so StrictMode's double mount makes one request, not two. */
  ensureLoaded: () => Promise<void>;
  /** Register a just-created source and start following its ingestion. */
  track: (asset: KnowledgeAsset) => void;
  upsert: (asset: KnowledgeAsset) => void;
  remove: (assetId: string) => void;
  /** Called when the session ends — stops polling and clears the library. */
  reset: () => void;
};

let inFlight: Promise<void> | null = null;

/**
 * One place the library lives, so the sidebar's "N working" badge, the composer's "answering
 * from N ready sources" hint, and the library page can't disagree with each other.
 */
export const useSourcesStore = create<SourcesState>()((set, get) => {
  /**
   * The only writer of `sources` — which is what lets `counts` be kept alongside it without
   * ever drifting, and what lets the counts object keep its identity while the four numbers
   * hold still.
   *
   * That identity is the whole point. `countByState` returns a fresh object every call, and
   * zustand v5 hands a selector's result straight to `useSyncExternalStore` with reference
   * equality and no caching — so deriving counts in a selector would both re-render every
   * subscriber on every poll tick and risk React's "getSnapshot should be cached" loop.
   * Previously a 2-second tick on one asset re-rendered every consumer of the sources
   * context, including AppShell (the entire tree) and every CitationCard in the open thread.
   */
  const commit = (next: KnowledgeAsset[]) => {
    const counts = countByState(next);
    const previous = get().counts;
    set({ sources: next, counts: sameCounts(previous, counts) ? previous : counts });
  };

  const handlers = {
    onUpdate: (asset: KnowledgeAsset) => get().upsert(asset),
    onReady: (asset: KnowledgeAsset) => toast.success(`“${sourceTitle(asset)}” is ready`),
    onLost: () =>
      toast.error("Lost track of an upload's progress — reload the page to check on it.")
  };

  return {
    sources: [],
    counts: EMPTY_COUNTS,
    loading: true,
    loaded: false,

    ensureLoaded: () => {
      if (get().loaded) return Promise.resolve();
      inFlight ??= (async () => {
        try {
          const assets = await api.listAssets();
          commit(assets);
          set({ loaded: true });
          // Resume following anything still in flight, e.g. after a reload.
          followAll(assets, handlers);
        } catch {
          // A failed load shows the empty state rather than an error banner, as before.
        } finally {
          set({ loading: false });
          inFlight = null;
        }
      })();
      return inFlight;
    },

    upsert: (asset) => {
      const current = get().sources;
      const index = current.findIndex((item) => item.id === asset.id);
      if (index === -1) {
        commit([asset, ...current]);
        return;
      }
      const next = [...current];
      next[index] = asset;
      commit(next);
    },

    remove: (assetId) => {
      unfollow(assetId);
      commit(get().sources.filter((item) => item.id !== assetId));
    },

    track: (asset) => {
      get().upsert(asset);
      follow(asset.id, handlers);
    },

    reset: () => {
      stopAll();
      inFlight = null;
      // EMPTY_COUNTS is reused so even the cleared counts keep a stable identity.
      set({ sources: [], counts: EMPTY_COUNTS, loading: true, loaded: false });
    }
  };
});
