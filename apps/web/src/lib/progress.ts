import type { KnowledgeAsset } from "@/types/api";
import { TERMINAL_STATUSES } from "@/types/api";

// Maps an asset's pipeline stage to a progress percentage for the bar. The stages
// are queued → extracting → chunking → embedding → ready, with failed terminal.
const STAGE_PCT: Record<string, number> = {
  pending: 5,
  queued: 8,
  extracting: 35,
  chunking: 62,
  embedding: 88,
  ready: 100,
  failed: 100
};

export function progressForStatus(status: string): number {
  return STAGE_PCT[status] ?? 8;
}

export function isTerminal(status: string): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status);
}

export function isProcessing(status: string): boolean {
  return !isTerminal(status);
}

// Human label for the current stage.
export function stageLabel(status: string): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "extracting":
      return "Extracting text";
    case "chunking":
      return "Splitting into passages";
    case "embedding":
      return "Generating embeddings";
    case "ready":
      return "Ready";
    case "failed":
      return "Failed";
    default:
      return status;
  }
}

export function countByState(assets: KnowledgeAsset[]) {
  let ready = 0;
  let processing = 0;
  let failed = 0;
  for (const a of assets) {
    if (a.status === "ready") ready++;
    else if (a.status === "failed") failed++;
    else processing++;
  }
  return { total: assets.length, ready, processing, failed };
}
