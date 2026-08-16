"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { formatLocator, sourceTitle, typeCopy } from "@kb/shared";
import { Button, Label, Panel, Pill, Skeleton, SourceIcon, buttonClass } from "@kb/ui";
import type { Citation, Conversation, KnowledgeAsset, Passage } from "@/types/api";
import * as api from "@/lib/api";

/** YouTube ids are stashed on the asset at ingest time, so no URL parsing is needed here. */
function youtubeEmbed(source: KnowledgeAsset, startSeconds: number): string | null {
  const videoId = source.metadata?.["video_id"];
  if (typeof videoId !== "string" || !videoId) return null;
  return `https://www.youtube-nocookie.com/embed/${videoId}?start=${Math.max(0, startSeconds)}`;
}

function locatorSeconds(locator: Citation["locator"]): number {
  return locator?.type === "timestamp" ? Number(locator.value) || 0 : 0;
}

export default function SourceViewerPage() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const search = useSearchParams();
  const router = useRouter();

  const fromMessageId = search.get("from");
  const fromConversationId = search.get("conv");
  const citeIndex = search.get("cite");
  const initialIndex = Number(search.get("i") ?? 0);

  const [source, setSource] = useState<KnowledgeAsset | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [passages, setPassages] = useState<Passage[]>([]);
  const [index, setIndex] = useState(Number.isFinite(initialIndex) ? initialIndex : 0);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getAsset(sourceId)
      .then((asset) => {
        if (!cancelled) setSource(asset);
      })
      .catch(() => {
        if (!cancelled) setMissing(true);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  // The citation set comes from the answer the reader arrived from, so the stepper walks
  // that answer's citations rather than the whole source. The citation link carries the
  // thread id, so this is one fetch.
  useEffect(() => {
    if (!fromMessageId || !fromConversationId) return;
    let cancelled = false;
    api
      .getConversation(fromConversationId)
      .then((full) => {
        if (!cancelled) setConversation(full);
      })
      .catch(() => undefined); // Falls back to "opened directly", which the panel explains.
    return () => {
      cancelled = true;
    };
  }, [fromMessageId, fromConversationId]);

  const citations = useMemo<Citation[]>(() => {
    const message = conversation?.messages.find((item) => item.id === fromMessageId);
    if (message) return message.citations;
    return [];
  }, [conversation, fromMessageId]);

  const citation: Citation | undefined =
    citations[index] ??
    (citeIndex !== null
      ? citations.find((item) => String(item.chunk_index) === citeIndex)
      : undefined);

  const chunkIndex = citation?.chunk_index ?? (citeIndex !== null ? Number(citeIndex) : undefined);

  // The cited passage plus its neighbours — the "read it in context" part.
  useEffect(() => {
    let cancelled = false;
    api
      .getPassages(sourceId, Number.isFinite(chunkIndex) ? chunkIndex : undefined, 2)
      .then((rows) => {
        if (!cancelled) setPassages(rows);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [sourceId, chunkIndex]);

  const startSeconds = locatorSeconds(citation?.locator ?? null);
  const timestampsUnavailable = source?.metadata?.["timestamps"] === "unavailable";

  if (missing) {
    return (
      <div className="mx-auto max-w-md px-5 py-24 text-center">
        <h1 className="text-display-md">That source isn&apos;t here</h1>
        <p className="mt-2 text-sm text-muted-foreground">It may have been removed.</p>
        <Button className="mt-6" onClick={() => router.push("/library")}>
          Back to your library
        </Button>
      </div>
    );
  }

  if (!source) {
    return (
      <div className="space-y-4 px-5 py-8 md:px-8">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const title = sourceTitle(source);
  const embedUrl = source.source_type === "youtube" ? youtubeEmbed(source, startSeconds) : null;
  const cited = passages.find((passage) => passage.chunk_index === chunkIndex);
  const before = passages.filter((passage) => passage.chunk_index < (chunkIndex ?? -1));
  const after = passages.filter((passage) => passage.chunk_index > (chunkIndex ?? -1));

  return (
    <div className="min-h-dvh">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4 md:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <SourceIcon type={source.source_type} />
          <div className="min-w-0">
            <h1 className="truncate text-[17px] font-semibold">{title}</h1>
            <p className="truncate text-[12px] text-muted-foreground">
              {typeCopy[source.source_type]?.label ?? source.source_type} · {source.filename}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {citations.length > 1 ? (
            <div className="flex items-center gap-1 rounded-md border border-border bg-card px-2 py-1">
              <button
                type="button"
                aria-label="Previous citation"
                disabled={index === 0}
                onClick={() => setIndex((value) => Math.max(0, value - 1))}
                className="inline-flex size-7 items-center justify-center rounded disabled:opacity-40"
              >
                <ChevronLeft className="size-4" />
              </button>
              <span className="text-[12px] text-muted-foreground">
                Citation {index + 1} of {citations.length}
              </span>
              <button
                type="button"
                aria-label="Next citation"
                disabled={index >= citations.length - 1}
                onClick={() => setIndex((value) => Math.min(citations.length - 1, value + 1))}
                className="inline-flex size-7 items-center justify-center rounded disabled:opacity-40"
              >
                <ChevronRight className="size-4" />
              </button>
            </div>
          ) : null}
          {conversation ? (
            <Link
              href={`/c/${conversation.id}`}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-foreground px-3 text-[13px] font-medium text-background"
            >
              <ArrowLeft className="size-3.5" aria-hidden /> Back to the answer
            </Link>
          ) : null}
          <Link
            href={`/sources/${source.id}`}
            className="inline-flex h-9 items-center rounded-md border border-border-strong bg-card px-3 text-[13px] font-medium"
          >
            Source details
          </Link>
        </div>
      </header>

      <div className="grid gap-6 px-5 py-6 md:px-8 lg:grid-cols-[1.6fr_1fr]">
        <Panel className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-border bg-canvas-soft px-4 py-2.5">
            <span className="label-caps text-muted-foreground">
              {citation ? formatLocator(citation.locator) : "Whole document"}
            </span>
            <span className="font-mono text-[12px] text-muted-soft">
              {source.source_type === "pdf" && source.metadata?.["pages"]
                ? `of ${String(source.metadata["pages"])} pages`
                : source.source_type === "pptx" && source.metadata?.["slide_count"]
                  ? `of ${String(source.metadata["slide_count"])} slides`
                  : ""}
            </span>
          </div>

          {embedUrl ? (
            <div className="p-5">
              <div className="aspect-video overflow-hidden rounded-md">
                <iframe
                  src={embedUrl}
                  title={`${title} at ${formatLocator(citation?.locator ?? null)}`}
                  allow="accelerometer; clipboard-write; encrypted-media; picture-in-picture"
                  allowFullScreen
                  className="size-full border-0"
                />
              </div>
              <p className="mt-3 text-[12px] text-muted-foreground">
                Playing from {citation ? formatLocator(citation.locator) : "the start"} — the cited
                line is highlighted below.
              </p>
            </div>
          ) : null}

          {source.source_type === "audio" ? (
            <div className="p-5">
              <p className="text-[12px] text-muted-foreground">
                {timestampsUnavailable
                  ? "This recording was transcribed without timings."
                  : `From ${formatLocator(citation?.locator ?? null)} — the cited line is highlighted below.`}{" "}
                {source.transcript_url ? (
                  <>
                    Read the{" "}
                    <a href={source.transcript_url} target="_blank" rel="noreferrer" className="underline">
                      full transcript
                    </a>
                    .
                  </>
                ) : null}
              </p>
            </div>
          ) : null}

          <div className="space-y-4 p-6 text-[15px] leading-relaxed">
            {before.map((passage) => (
              <p key={passage.chunk_index} className="text-muted-foreground">
                {passage.text}
              </p>
            ))}

            <p className="rounded-md bg-primary/10 p-3 ring-1 ring-primary/30">
              <mark className="bg-transparent font-medium text-foreground">
                {cited?.text ??
                  citation?.excerpt ??
                  "Open this source from a citation to see the exact passage highlighted here."}
              </mark>
            </p>

            {after.map((passage) => (
              <p key={passage.chunk_index} className="text-muted-foreground">
                {passage.text}
              </p>
            ))}
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel className="p-5">
            <Label>This citation</Label>
            {citation ? (
              <>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Pill>{formatLocator(citation.locator)}</Pill>
                  <span className="text-[12px] text-muted-foreground">
                    {Math.round(citation.score * 100)}% relevance
                  </span>
                </div>
                <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">
                  Saga retrieved this passage because it was among the closest matches to your
                  question. Relevance is how close, not how correct — read it and decide.
                </p>
              </>
            ) : (
              <p className="mt-3 text-[13px] text-muted-foreground">
                You opened this source directly, so no passage is highlighted. Ask a question and
                open a citation to land on an exact spot.
              </p>
            )}
          </Panel>

          {citations.length > 1 ? (
            <Panel className="p-5">
              <Label>All citations in that answer</Label>
              <ol className="mt-3 space-y-2">
                {citations.map((item, position) => (
                  <li key={`${item.asset_id}-${item.chunk_index}`}>
                    <button
                      type="button"
                      onClick={() => setIndex(position)}
                      aria-current={position === index ? "true" : undefined}
                      className={`w-full rounded-md border p-3 text-left text-[13px] ${
                        position === index
                          ? "border-foreground"
                          : "border-border hover:border-border-strong"
                      }`}
                    >
                      <span className="font-semibold">{formatLocator(item.locator)}</span>
                      <span className="mt-1 line-clamp-2 block text-muted-foreground">
                        “{item.excerpt}”
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            </Panel>
          ) : null}

          {source.transcript_url ? (
            <a
              href={source.transcript_url}
              target="_blank"
              rel="noreferrer"
              className={buttonClass("secondary", "md", "w-full")}
            >
              Read the full transcript
            </a>
          ) : null}

          {source.download_url ? (
            <a
              href={source.download_url}
              download
              className={buttonClass("secondary", "md", "w-full")}
            >
              Download the original
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}
