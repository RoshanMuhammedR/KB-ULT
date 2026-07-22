import { cn } from "@kb/ui";
import type { KnowledgeAsset } from "@/types/api";
import { countByState } from "@/lib/progress";

export function StatTiles({ assets }: { assets: KnowledgeAsset[] }) {
  const c = countByState(assets);
  const tiles = [
    { k: "Sources", n: c.total, cls: "" },
    { k: "Ready", n: c.ready, cls: "stat--ready" },
    { k: "Processing", n: c.processing, cls: "" },
    { k: "Failed", n: c.failed, cls: "stat--failed" }
  ];
  return (
    <div className="stats">
      {tiles.map((t) => (
        <div className={cn("stat", t.cls)} key={t.k}>
          <div className="stat__n">{t.n}</div>
          <div className="stat__k">{t.k}</div>
        </div>
      ))}
    </div>
  );
}
