"use client";

import { useEffect, useMemo, useRef } from "react";
import { formatLocator } from "@kb/shared";
import type { KnowledgeAsset, Locator, Region, TimelineRegion } from "@/types/api";

/** Narrow the region union — a timeline region is the one carrying `start`. */
function isTimeline(region: Region): region is TimelineRegion {
  return "start" in region && typeof (region as TimelineRegion).start === "number";
}

/** YouTube ids are stashed on the asset at ingest time, so no URL parsing is needed here. */
function youtubeEmbed(source: KnowledgeAsset, startSeconds: number, endSeconds?: number): string | null {
  const videoId = source.metadata?.["video_id"];
  if (typeof videoId !== "string" || !videoId) return null;
  const params = new URLSearchParams({ start: String(Math.max(0, Math.floor(startSeconds))) });
  // YouTube's own `end` param stops playback at the passage's end, so the embed honours the
  // cited span rather than just its first second.
  if (endSeconds && endSeconds > startSeconds) {
    params.set("end", String(Math.ceil(endSeconds)));
  }
  return `https://www.youtube-nocookie.com/embed/${videoId}?${params.toString()}`;
}

function clock(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(rest)}` : `${minutes}:${pad(rest)}`;
}

/**
 * A source that has a playhead: uploaded audio or a YouTube video.
 *
 * One component for both, because from the reader's point of view they are the same thing —
 * a passage that starts at one second and ends at another. Only the player element differs.
 *
 * The passage span comes from `regions` ({start, end} in float seconds) when the pipeline
 * captured it. Older sources have only the locator's integer start, in which case the
 * component seeks there and simply shows no end — an honest degradation rather than a
 * guessed duration.
 */
export function TimelineViewer({
  source,
  regions,
  locator,
  downloadUrl
}: {
  source: KnowledgeAsset;
  regions?: Region[];
  locator: Locator;
  downloadUrl: string | null;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const span = useMemo(() => {
    const timeline = (regions ?? []).filter(isTimeline);
    if (timeline.length > 0) return timeline[0]!;
    // No captured region: fall back to the locator's whole-second start, with no end.
    const start = locator?.type === "timestamp" ? Number(locator.value) || 0 : 0;
    return { start, end: 0 } as TimelineRegion;
  }, [regions, locator]);

  // The pipeline sets this when the provider returned no per-line timings at all, so any
  // timestamp shown would be invented. Honoured here rather than seeking to a fictional
  // second — this check predates the region work and must survive it.
  const timestampsUnavailable = source.metadata?.["timestamps"] === "unavailable";

  const embedUrl =
    source.source_type === "youtube"
      ? youtubeEmbed(source, timestampsUnavailable ? 0 : span.start, span.end || undefined)
      : null;

  useEffect(() => {
    const element = audioRef.current;
    if (!element || timestampsUnavailable || span.start <= 0) return;
    const seek = () => {
      element.currentTime = span.start;
    };
    if (element.readyState >= 1) seek();
    else element.addEventListener("loadedmetadata", seek, { once: true });
  }, [span.start, timestampsUnavailable, downloadUrl]);

  const caption = timestampsUnavailable
    ? "This recording was transcribed without timings, so the player starts at the beginning."
    : span.end > span.start
      ? `Playing ${clock(span.start)} – ${clock(span.end)} — the cited passage is highlighted below.`
      : `Starting at ${formatLocator(locator)} — the cited passage is highlighted below.`;

  if (embedUrl) {
    return (
      <div className="p-5">
        <div className="aspect-video overflow-hidden rounded-md">
          <iframe
            src={embedUrl}
            title={`${source.title ?? source.filename} at ${formatLocator(locator)}`}
            allow="accelerometer; clipboard-write; encrypted-media; picture-in-picture"
            allowFullScreen
            className="size-full border-0"
          />
        </div>
        <p className="mt-3 text-[12px] text-muted-foreground">{caption}</p>
      </div>
    );
  }

  if (source.source_type === "audio" && downloadUrl) {
    return (
      <div className="p-5">
        <audio ref={audioRef} controls preload="metadata" src={downloadUrl} className="w-full">
          Your browser can&apos;t play this recording.
        </audio>
        <p className="mt-3 text-[12px] text-muted-foreground">{caption}</p>
      </div>
    );
  }

  return null;
}
