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

export const DEMO_QUESTION = "What drove the margin decline at Northwind in Q2?";

export const DEMO_ANSWER = `Two things, and the filing separates them clearly. The larger share came from freight: contracted haulage rates rose 11% year on year after the Q1 renewals, which Northwind absorbed rather than passing on to shippers already under contract.

The second was mix. Bonded warehousing — the highest-margin line — grew more slowly than general fulfilment, so the blended margin fell even where individual lines held. Management expects the freight effect to persist into Q3 and the mix effect to reverse as the Rotterdam bonded capacity comes online.`;

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

export const DEMO_INSUFFICIENT = `I couldn't answer this from your sources. Nothing in your library discusses pricing strategy closely enough for me to quote it — the closest material is the Meridian onboarding deck, which covers engagement scope but not pricing.`;
