import type { Locator, SourceType } from "@kb/shared";

/**
 * Static sample content for the marketing page only.
 *
 * Deliberately its own module rather than anything shared with the product app: nothing here
 * should ever be mistaken for, or drift into, real user data.
 */

export type DemoCitation = {
  filename: string;
  source_type: SourceType;
  locator: Locator;
  chunk_index: number;
  score: number;
  excerpt: string;
};

export const DEMO_CITATIONS: DemoCitation[] = [
  {
    filename: "northwind-q2-2026-10q.pdf",
    source_type: "pdf",
    locator: { type: "page", value: 14 },
    chunk_index: 61,
    score: 0.89,
    excerpt:
      "Contracted haulage rates increased 11.2% year on year following the Q1 renewal cycle. The Company elected to absorb the increase for shippers under existing contract terms, which reduced gross margin by approximately 180 basis points."
  },
  {
    filename: "northwind-q2-2026-10q.pdf",
    source_type: "pdf",
    locator: { type: "page", value: 22 },
    chunk_index: 94,
    score: 0.81,
    excerpt:
      "Bonded warehousing revenue grew 4% against 19% for general fulfilment. As bonded carries a materially higher margin, the shift in mix reduced blended gross margin independently of any change within individual service lines."
  },
  {
    filename: "northwind-q2-earnings-call.mp3",
    source_type: "audio",
    locator: { type: "timestamp", value: 1447 },
    chunk_index: 38,
    score: 0.74,
    excerpt:
      "On freight, assume that persists through the third quarter. On mix, Rotterdam comes online in September and we'd expect the bonded share to recover from there."
  }
];

export const DEMO_LIBRARY: { title: string; source_type: SourceType }[] = [
  { title: "Northwind Logistics — Q2 2026 filing", source_type: "pdf" },
  { title: "Northwind Q2 earnings call", source_type: "audio" },
  { title: "Meridian onboarding deck", source_type: "pptx" },
  { title: "Freight market outlook 2026", source_type: "youtube" },
  { title: "Discovery notes — Rotterdam", source_type: "markdown" }
];

/** The question the hero's terminal types out; the citations above are what it retrieves. */
export const DEMO_QUESTION = "What drove the margin decline at Northwind in Q2?";
