"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Skeleton } from "@kb/ui";
import type { PageManifestEntry, PagedRegion, Region } from "@/types/api";
import * as api from "@/lib/api";

/** Narrow the region union — a paged region is the one carrying `rects`. */
function isPaged(region: Region): region is PagedRegion {
  return "rects" in region && Array.isArray((region as PagedRegion).rects);
}

/**
 * A source that has pages, with the cited passage highlighted on the page image.
 *
 * Highlights are positioned in percentages, not pixels. The API sends rects as fractions of
 * the page box, so `left: 11.8%` lands on the same words whether the image is rendered at
 * 400px or 4000px wide — the browser's own layout does the scaling, and there is nothing to
 * recompute on resize, zoom, or rotation.
 *
 * This component is deliberately format-blind: a PDF page (JPEG) and a PowerPoint slide (SVG
 * reconstruction) are both just an image URL with a size, so adding a format server-side
 * needs no change here.
 */
export function PagedViewer({
  assetId,
  pages,
  regions,
  label
}: {
  assetId: string;
  pages: PageManifestEntry[];
  regions?: Region[];
  label: string;
}) {
  const highlights = useMemo(() => (regions ?? []).filter(isPaged), [regions]);

  // Open on the cited page; without a citation, open at the beginning.
  const initialPage = highlights[0]?.page ?? pages[0]?.n ?? 1;
  const [page, setPage] = useState(initialPage);
  const [rendered, setRendered] = useState<{ url: string; page: number } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setPage(initialPage);
  }, [initialPage]);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    api
      .getRenderedPage(assetId, page)
      .then((result) => {
        if (!cancelled) setRendered({ url: result.url, page });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [assetId, page]);

  const entry = pages.find((item) => item.n === page) ?? pages[0];
  const aspect = entry && entry.w > 0 ? entry.h / entry.w : 1.294; // US Letter fallback
  const onThisPage = highlights.filter((region) => region.page === page);
  const positions = pages.map((item) => item.n);
  const cursor = positions.indexOf(page);

  return (
    <div className="p-5">
      <div className="flex items-center justify-between pb-3">
        <span className="font-mono text-[12px] text-muted-soft">
          Page {page} of {pages.length}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setPage(positions[Math.max(0, cursor - 1)] ?? page)}
            disabled={cursor <= 0}
            aria-label="Previous page"
            className="rounded-md p-1.5 hover:bg-muted disabled:opacity-40"
          >
            <ChevronLeft className="size-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => setPage(positions[Math.min(positions.length - 1, cursor + 1)] ?? page)}
            disabled={cursor >= positions.length - 1}
            aria-label="Next page"
            className="rounded-md p-1.5 hover:bg-muted disabled:opacity-40"
          >
            <ChevronRight className="size-4" aria-hidden />
          </button>
        </div>
      </div>

      {/* The wrapper owns the aspect ratio so the highlight boxes have something correctly
          shaped to sit on even before the image bytes arrive — no jump when it loads. */}
      <div
        className="relative w-full overflow-hidden rounded-md border border-border bg-canvas-soft"
        style={{ aspectRatio: `${1} / ${aspect}` }}
      >
        {rendered?.page === page ? (
          <img
            src={rendered.url}
            alt={`${label}, page ${page}`}
            className="size-full object-contain"
            onError={() => setFailed(true)}
          />
        ) : failed ? (
          <div className="flex size-full items-center justify-center p-6 text-center">
            <p className="text-[13px] text-muted-foreground">
              This page image couldn&apos;t be loaded. The text of the passage is below.
            </p>
          </div>
        ) : (
          <Skeleton className="size-full" />
        )}

        {onThisPage.map((region, regionIndex) =>
          region.rects.map(([x0, y0, x1, y1], rectIndex) => (
            <span
              key={`${regionIndex}-${rectIndex}`}
              aria-hidden
              className="pointer-events-none absolute rounded-[2px] bg-primary/25 ring-1 ring-primary/50"
              style={{
                left: `${x0 * 100}%`,
                top: `${y0 * 100}%`,
                width: `${Math.max(0, x1 - x0) * 100}%`,
                height: `${Math.max(0, y1 - y0) * 100}%`
              }}
            />
          ))
        )}
      </div>

      {highlights.length > 1 ? (
        <p className="mt-3 text-[12px] text-muted-foreground">
          This passage runs across pages {highlights.map((region) => region.page).join(" and ")}.
        </p>
      ) : null}
    </div>
  );
}
