"use client";

import { useState } from "react";
import { time } from "@kb/shared";
import { Panel } from "@kb/ui";
import type { JobEvent, KnowledgeAsset } from "@/types/api";

type Tone = "info" | "warn" | "error" | "ok";

/**
 * Turns a worker log line into a sentence a person would write.
 *
 * The raw event names are pipeline vocabulary ("chunking", "embedding", attempt counters) and
 * the product's rule is that those never lead. The original payload is still one click away
 * behind "Show technical detail" — transparency, without internals-as-UI.
 */
function describe(event: JobEvent, source: KnowledgeAsset): { text: string; tone: Tone } {
  switch (event.event) {
    case "queued":
      return { text: "Added to your library and queued for preparation.", tone: "info" };
    case "retry":
      return { text: "You asked to try again — it went back in the queue.", tone: "info" };
    case "running":
      return { text: "Preparation started.", tone: "info" };
    case "extracting":
      return {
        text:
          source.source_type === "audio"
            ? "Transcribing the recording. This is the slow part."
            : source.source_type === "youtube"
              ? "Fetching the transcript for this video."
              : "Reading the text out of the file.",
        tone: "info"
      };
    case "chunking":
      return { text: "Breaking the text into quotable passages.", tone: "info" };
    case "embedding":
      return {
        text:
          typeof event.data?.["chunk_count"] === "number"
            ? `Making ${event.data["chunk_count"]} passages searchable.`
            : "Making the passages searchable.",
        tone: "info"
      };
    case "ready":
      return { text: "Ready — answers can now cite this source.", tone: "ok" };
    case "failed":
      return {
        text: event.message ?? "Something went wrong while preparing this source.",
        tone: "error"
      };
    default:
      return { text: event.message ?? event.event, tone: event.level === "error" ? "error" : "info" };
  }
}

const DOT: Record<Tone, string> = {
  error: "bg-destructive",
  warn: "bg-stage-queued",
  ok: "bg-success",
  info: "bg-stage-reading"
};

export function ActivityTimeline({
  events,
  source
}: {
  events: JobEvent[];
  source: KnowledgeAsset;
}) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <Panel className="p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[18px] font-semibold">What&apos;s happened to this source</h2>
        <button
          type="button"
          onClick={() => setShowRaw((value) => !value)}
          aria-expanded={showRaw}
          className="text-[13px] font-medium text-muted-foreground hover:text-foreground"
        >
          {showRaw ? "Hide technical detail" : "Show technical detail"}
        </button>
      </div>

      {events.length === 0 ? (
        <p className="mt-4 text-[13px] text-muted-foreground">
          Nothing recorded yet. This fills in as the source is prepared.
        </p>
      ) : (
        <ol className="mt-4 space-y-4">
          {events.map((event) => {
            const { text, tone } = describe(event, source);
            return (
              <li key={event.id} className="flex gap-3">
                <span aria-hidden className={`mt-1.5 size-2 shrink-0 rounded-full ${DOT[tone]}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-[14px]">
                    {tone === "warn" ? <span className="sr-only">Warning: </span> : null}
                    {tone === "error" ? <span className="sr-only">Failed: </span> : null}
                    {text}
                  </p>
                  {event.ts ? <p className="text-[12px] text-muted-soft">{time(event.ts)}</p> : null}
                  {showRaw ? (
                    <pre className="mt-2 overflow-x-auto rounded-md bg-canvas-soft p-3 font-mono text-[11px] text-muted-foreground">
                      {JSON.stringify(
                        { event: event.event, level: event.level, message: event.message, ...event.data },
                        null,
                        2
                      )}
                    </pre>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
