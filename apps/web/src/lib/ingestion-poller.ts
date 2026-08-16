// Follows sources through ingestion until they reach a terminal state.
//
// Deliberately not a hook. Ingestion outlives any one component: an upload started on the
// library page must keep being followed while the user reads a thread. That also means there
// is no unmount to hang cleanup on any more, so cancellation is explicit — see `stopAll`.
//
// React-free on purpose, so the store can own it without this module needing to import the
// store back (handlers are passed per call instead).
import { isProcessing, isTerminal } from "@kb/shared";
import type { KnowledgeAsset } from "@/types/api";
import * as api from "@/lib/api";

const POLL_INTERVAL_MS = 2000;
// A poll can fail transiently (sleeping laptop, flaky wifi) without the source itself being
// in trouble, so a few failures in a row are tolerated before we admit we've lost track.
const MAX_CONSECUTIVE_FAILURES = 5;

export type PollHandlers = {
  onUpdate: (asset: KnowledgeAsset) => void;
  onReady?: (asset: KnowledgeAsset) => void;
  onLost?: (asset: KnowledgeAsset) => void;
};

const tracked = new Set<string>();

// A generation counter rather than a `cancelled` boolean. At module scope a boolean would be
// a one-way latch: the first sign-out would disable polling for the life of the tab, so
// signing back in would give you a library that silently never updates. Bumping the
// generation retires the loops in flight and leaves the module usable.
let generation = 0;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function follow(assetId: string, handlers: PollHandlers): void {
  if (tracked.has(assetId)) return; // already being followed
  tracked.add(assetId);

  const mine = generation;
  const live = () => mine === generation && tracked.has(assetId);

  void (async () => {
    let failures = 0;
    try {
      while (live()) {
        await sleep(POLL_INTERVAL_MS);
        if (!live()) return;

        let asset: KnowledgeAsset;
        try {
          asset = await api.getAsset(assetId);
          failures = 0;
        } catch {
          failures += 1;
          if (failures >= MAX_CONSECUTIVE_FAILURES) {
            if (live()) handlers.onLost?.({ id: assetId } as KnowledgeAsset);
            return;
          }
          continue;
        }

        if (!live()) return;
        handlers.onUpdate(asset);
        if (isTerminal(asset.status)) {
          if (asset.status === "ready") handlers.onReady?.(asset);
          return;
        }
      }
    } finally {
      // Only if we are still the current generation: a retired loop must not delete an entry
      // that a post-sign-in loop for the same asset has since re-added, or dedupe breaks.
      if (mine === generation) tracked.delete(assetId);
    }
  })();
}

/** Resume following everything still in flight — e.g. after a reload. */
export function followAll(assets: KnowledgeAsset[], handlers: PollHandlers): void {
  for (const asset of assets) {
    if (isProcessing(asset.status)) follow(asset.id, handlers);
  }
}

/** Stop following one source — e.g. the user deleted it mid-ingest. */
export function unfollow(assetId: string): void {
  tracked.delete(assetId);
}

/**
 * Retire every loop. Called when the session ends: without it, a soft sign-out
 * (`router.replace`, which keeps the JS realm alive) would leave 2-second loops polling
 * forever against a dead token. The module stays reusable afterwards.
 */
export function stopAll(): void {
  generation += 1;
  tracked.clear();
}
