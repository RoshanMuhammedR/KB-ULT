"use client";

import { MemoryPanel } from "@/components/saga/memory-panel";
import { RoutePage } from "@/components/saga/route-overlay";

/** /memory opened cold. From inside the app it renders as a drawer instead — see @modal. */
export default function MemoryPage() {
  return (
    <RoutePage
      title="Memory"
      description="Facts Saga has picked up about you and your work. It uses these as background in future answers — never as a source it cites."
    >
      <MemoryPanel />
    </RoutePage>
  );
}
