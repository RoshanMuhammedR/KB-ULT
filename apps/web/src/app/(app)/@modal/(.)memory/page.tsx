"use client";

import { MemoryPanel } from "@/components/saga/memory-panel";
import { RouteOverlay } from "@/components/saga/route-overlay";

/**
 * /memory over whatever you were reading.
 *
 * A drawer rather than a centred dialog: checking what Saga remembers is something you do
 * *about* an answer, so the answer should stay visible beside it.
 */
export default function MemoryOverlay() {
  return (
    <RouteOverlay
      href="/memory"
      title="Memory"
      subtitle="Background for answers, never a cited source"
      placement="right"
    >
      <MemoryPanel compact />
    </RouteOverlay>
  );
}
