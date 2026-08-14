/**
 * The product's user-facing vocabulary for sources.
 *
 * This module is the single place where pipeline stages become plain language. The API
 * speaks in stage names (`extracting`, `chunking`, `embedding`); the UI never does. If a
 * label needs to change, it changes here and both apps follow.
 */

export type SourceType = "pdf" | "youtube" | "markdown" | "pptx" | "audio";

/**
 * Mirrors `AssetStatus` in apps/api/src/domain/entities/knowledge_asset.py. `pending` is the
 * row's initial state before it reaches the queue; users can't tell it apart from `queued`,
 * so it reads the same.
 */
export type SourceStatus =
  | "pending"
  | "queued"
  | "extracting"
  | "chunking"
  | "embedding"
  | "ready"
  | "failed";

export const SOURCE_STATUSES: readonly SourceStatus[] = [
  "pending",
  "queued",
  "extracting",
  "chunking",
  "embedding",
  "ready",
  "failed"
];

/** Where inside a source a passage came from. `null` means the source has no positions. */
export type Locator =
  | { type: "page"; value: number }
  | { type: "timestamp"; value: number }
  | { type: "slide"; value: number }
  | { type: "section"; value: string }
  | null;

export type StatusTone = "pending" | "active" | "ready" | "failed";

/** Human-facing label for a source status. No pipeline vocabulary. */
export const statusCopy: Record<
  SourceStatus,
  { label: string; hint: string; tone: StatusTone }
> = {
  pending: { label: "Waiting to start", hint: "In line — starting shortly.", tone: "pending" },
  queued: { label: "Waiting to start", hint: "In line — starting shortly.", tone: "pending" },
  extracting: { label: "Reading the file", hint: "Pulling the text out.", tone: "active" },
  chunking: {
    label: "Breaking into passages",
    hint: "Splitting it into quotable pieces.",
    tone: "active"
  },
  embedding: {
    label: "Making it searchable",
    hint: "Almost done — indexing passages.",
    tone: "active"
  },
  ready: { label: "Ready to use", hint: "Answers can cite this source.", tone: "ready" },
  failed: {
    label: "Couldn't be added",
    hint: "Something went wrong — you can retry.",
    tone: "failed"
  }
};

export const typeCopy: Record<SourceType, { label: string; locator: string }> = {
  pdf: { label: "PDF", locator: "page" },
  youtube: { label: "Video", locator: "timestamp" },
  markdown: { label: "Markdown", locator: "section" },
  pptx: { label: "Slides", locator: "slide" },
  audio: { label: "Audio", locator: "timestamp" }
};

/** Progress percentage for the bar, keyed by pipeline stage. */
const STAGE_PCT: Record<SourceStatus, number> = {
  pending: 5,
  queued: 8,
  extracting: 35,
  chunking: 62,
  embedding: 88,
  ready: 100,
  failed: 100
};

const TERMINAL_STATUSES: readonly string[] = ["ready", "failed"];

export function progressForStatus(status: string): number {
  return STAGE_PCT[status as SourceStatus] ?? 8;
}

/** 0–1, which is what `ProgressBar` takes. */
export function progressFraction(status: string): number {
  return progressForStatus(status) / 100;
}

export function isTerminal(status: string): boolean {
  return TERMINAL_STATUSES.includes(status);
}

export function isProcessing(status: string): boolean {
  return !isTerminal(status);
}

export function statusLabel(status: string): string {
  return statusCopy[status as SourceStatus]?.label ?? "Working on it";
}

export function statusHint(status: string): string {
  return statusCopy[status as SourceStatus]?.hint ?? "";
}

export function statusTone(status: string): StatusTone {
  return statusCopy[status as SourceStatus]?.tone ?? "active";
}

export function formatLocator(locator: Locator): string {
  if (!locator) return "Whole document";
  if (locator.type === "page") return `Page ${locator.value}`;
  if (locator.type === "slide") return `Slide ${locator.value}`;
  if (locator.type === "section") return locator.value;
  const minutes = Math.floor(locator.value / 60);
  const seconds = Math.floor(locator.value % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** Falls back to the filename — the API leaves `title` null when it can't extract one. */
export function sourceTitle(source: { title: string | null; filename: string }): string {
  return source.title ?? source.filename;
}

export function countByState(sources: readonly { status: string }[]) {
  let ready = 0;
  let processing = 0;
  let failed = 0;
  for (const source of sources) {
    if (source.status === "ready") ready++;
    else if (source.status === "failed") failed++;
    else processing++;
  }
  return { total: sources.length, ready, processing, failed };
}
