"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";
import { countByState, sourceTitle } from "@kb/shared";
import type { KnowledgeAsset } from "@/types/api";
import * as api from "@/lib/api";
import { useIngestionPoll } from "@/lib/use-ingestion-poll";
import { useToast } from "@/lib/toast";

type SourcesValue = {
  sources: KnowledgeAsset[];
  loading: boolean;
  error: string | null;
  counts: { total: number; ready: number; processing: number; failed: number };
  refresh: () => Promise<void>;
  /** Register a just-created source and start following its ingestion. */
  track: (asset: KnowledgeAsset) => void;
  upsert: (asset: KnowledgeAsset) => void;
  remove: (assetId: string) => void;
};

const SourcesContext = createContext<SourcesValue | null>(null);

/**
 * One place the library lives, so the sidebar's "N working" badge, the composer's "answering
 * from N ready sources" hint, and the library page can't disagree with each other.
 */
export function SourcesProvider({ children }: { children: React.ReactNode }) {
  const [sources, setSources] = useState<KnowledgeAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const upsert = useCallback((asset: KnowledgeAsset) => {
    setSources((current) => {
      const index = current.findIndex((item) => item.id === asset.id);
      if (index === -1) return [asset, ...current];
      const next = [...current];
      next[index] = asset;
      return next;
    });
  }, []);

  const remove = useCallback((assetId: string) => {
    setSources((current) => current.filter((item) => item.id !== assetId));
  }, []);

  const { follow, followAll } = useIngestionPoll({
    onUpdate: upsert,
    onReady: (asset) => toast.success(`“${sourceTitle(asset)}” is ready`),
    onLost: () =>
      toast.error("Lost track of an upload's progress — reload the page to check on it.")
  });

  const refresh = useCallback(async () => {
    try {
      const assets = await api.listAssets();
      setSources(assets);
      setError(null);
      // Resume following anything still in flight, e.g. after a reload.
      followAll(assets);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your library.");
    } finally {
      setLoading(false);
    }
  }, [followAll]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const track = useCallback(
    (asset: KnowledgeAsset) => {
      upsert(asset);
      follow(asset.id);
    },
    [follow, upsert]
  );

  const value = useMemo<SourcesValue>(
    () => ({
      sources,
      loading,
      error,
      counts: countByState(sources),
      refresh,
      track,
      upsert,
      remove
    }),
    [sources, loading, error, refresh, track, upsert, remove]
  );

  return <SourcesContext.Provider value={value}>{children}</SourcesContext.Provider>;
}

export function useSources(): SourcesValue {
  const ctx = useContext(SourcesContext);
  if (!ctx) throw new Error("useSources must be used within SourcesProvider");
  return ctx;
}
