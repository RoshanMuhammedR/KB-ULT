"use client";

import { useCallback, useEffect, useRef } from "react";
import { isProcessing, isTerminal, sourceTitle } from "@kb/shared";
import type { KnowledgeAsset } from "@/types/api";
import * as api from "@/lib/api";

const POLL_INTERVAL_MS = 2000;
// A poll can fail transiently (sleeping laptop, flaky wifi) without the source itself being
// in trouble, so a few failures in a row are tolerated before we admit we've lost track.
const MAX_CONSECUTIVE_FAILURES = 5;

type Options = {
  onUpdate: (asset: KnowledgeAsset) => void;
  onReady?: (asset: KnowledgeAsset) => void;
  onLost?: (asset: KnowledgeAsset) => void;
};

/**
 * Follows sources through ingestion until they reach a terminal state.
 *
 * Ingestion is asynchronous and is the single most important interaction in the product —
 * a user watching an upload needs to see it actually moving. This polls `GET /documents/{id}`
 * and reports each change upward.
 *
 * Two things it is careful about, which the original inline version was not:
 *   * it stops on unmount, rather than looping against a dead component, and
 *   * it refuses to start a second loop for a source it is already following.
 */
export function useIngestionPoll({ onUpdate, onReady, onLost }: Options) {
  const tracked = useRef(new Set<string>());
  const cancelled = useRef(false);
  // Kept in refs so `follow` stays referentially stable across renders — otherwise every
  // parent re-render would restart the effects that call it.
  const handlers = useRef({ onUpdate, onReady, onLost });
  handlers.current = { onUpdate, onReady, onLost };

  useEffect(() => {
    cancelled.current = false;
    const active = tracked.current;
    return () => {
      cancelled.current = true;
      active.clear();
    };
  }, []);

  const follow = useCallback((assetId: string) => {
    if (tracked.current.has(assetId)) return; // already being followed
    tracked.current.add(assetId);

    void (async () => {
      let failures = 0;
      try {
        while (!cancelled.current) {
          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
          if (cancelled.current) return;

          let asset: KnowledgeAsset;
          try {
            asset = await api.getAsset(assetId);
            failures = 0;
          } catch {
            failures += 1;
            if (failures >= MAX_CONSECUTIVE_FAILURES) {
              handlers.current.onLost?.({ id: assetId } as KnowledgeAsset);
              return;
            }
            continue;
          }

          if (cancelled.current) return;
          handlers.current.onUpdate(asset);
          if (isTerminal(asset.status)) {
            if (asset.status === "ready") handlers.current.onReady?.(asset);
            return;
          }
        }
      } finally {
        tracked.current.delete(assetId);
      }
    })();
  }, []);

  /** Resume following everything still in flight — e.g. after a reload. */
  const followAll = useCallback(
    (assets: KnowledgeAsset[]) => {
      for (const asset of assets) {
        if (isProcessing(asset.status)) follow(asset.id);
      }
    },
    [follow]
  );

  return { follow, followAll };
}

export { sourceTitle };
