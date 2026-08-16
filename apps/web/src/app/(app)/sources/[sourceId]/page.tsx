"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Download, Eye, Pencil, RefreshCw, Trash2 } from "lucide-react";
import {
  formatLocator,
  isProcessing,
  progressFraction,
  relative,
  sourceTitle,
  statusCopy,
  typeCopy
} from "@kb/shared";
import {
  Button,
  ConfirmDialog,
  Input,
  buttonClass,
  Label,
  Panel,
  Pill,
  ProgressBar,
  Skeleton,
  SourceIcon,
  StatusBadge
} from "@kb/ui";
import { AppHeader } from "@/components/saga/app-shell";
import { ActivityTimeline } from "@/components/saga/activity-timeline";
import type { AssetCitation, JobEvent, KnowledgeAsset } from "@/types/api";
import * as api from "@/lib/api";
import { useSources } from "@/lib/sources-context";
import { useToast } from "@/lib/toast";

// Metadata keys that are plumbing, not information a reader wants.
// The parsed source itself is no longer in here to hide: it moved to its own server-side
// column, so the whole text of every document stopped being shipped on each status poll.
const HIDDEN_METADATA = new Set([
  "transcript_key",
  "source_type",
  "filename",
  "title",
  "parser",
  "content_type",
  "format"
]);

export default function SourceDetailPage() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const router = useRouter();
  const toast = useToast();
  const { sources, track, remove } = useSources();

  const [source, setSource] = useState<KnowledgeAsset | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [cited, setCited] = useState<AssetCitation[]>([]);
  const [missing, setMissing] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      const asset = await api.getAsset(sourceId);
      setSource(asset);
      const [eventList, citationList] = await Promise.all([
        api.getAssetEvents(sourceId).catch(() => []),
        api.getAssetCitations(sourceId).catch(() => [])
      ]);
      setEvents(eventList);
      setCited(citationList);
    } catch {
      setMissing(true);
    }
  }, [sourceId]);

  useEffect(() => {
    void load();
  }, [load]);

  // While it's still being prepared, mirror the shared poller's view of it.
  const live = sources.find((item) => item.id === sourceId);
  useEffect(() => {
    if (live) setSource(live);
  }, [live]);

  // Refresh the timeline when it reaches a terminal state, so the last lines appear.
  useEffect(() => {
    if (source && !isProcessing(source.status)) {
      void api.getAssetEvents(sourceId).then(setEvents).catch(() => undefined);
    }
  }, [source?.status, sourceId, source]);

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
        <Skeleton className="h-32" />
      </div>
    );
  }

  const title = sourceTitle(source);
  const working = isProcessing(source.status);

  async function commitRename() {
    const next = draft.trim();
    setRenaming(false);
    if (!next || !source || next === source.title) return;
    try {
      const updated = await api.renameAsset(source.id, next);
      setSource(updated);
      track(updated);
    } catch {
      toast.error("Couldn't rename that source.");
    }
  }

  async function retry() {
    if (!source) return;
    try {
      const updated = await api.retryAsset(source.id);
      setSource(updated);
      track(updated);
    } catch {
      toast.error("Couldn't start that again.");
    }
  }

  async function confirmDelete() {
    if (!source) return;
    setDeleting(true);
    try {
      await api.deleteAsset(source.id);
      remove(source.id);
      toast.success(`“${title}” was removed.`);
      router.replace("/library");
    } catch {
      toast.error("Couldn't remove that source.");
      setDeleting(false);
    }
  }

  const metadata = Object.entries(source.metadata ?? {}).filter(
    ([key, value]) =>
      !HIDDEN_METADATA.has(key) && value !== null && value !== "" && typeof value !== "object"
  );

  return (
    <div>
      <div className="px-5 pt-6 md:px-8">
        <Link
          href="/library"
          className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" aria-hidden /> Back to your library
        </Link>
      </div>

      <AppHeader
        title={title}
        description={`${typeCopy[source.source_type]?.label ?? source.source_type} · ${source.filename}${
          source.created_at ? ` · added ${relative(source.created_at)}` : ""
        }`}
        actions={
          <>
            {source.status === "ready" ? (
              <Button variant="secondary" size="sm" onClick={() => router.push(`/view/${source.id}`)}>
                <Eye className="size-3.5" aria-hidden /> Open source
              </Button>
            ) : null}
            {source.status === "failed" ? (
              <Button variant="secondary" size="sm" onClick={() => void retry()}>
                <RefreshCw className="size-3.5" aria-hidden /> Try again
              </Button>
            ) : null}
            {source.download_url ? (
              // A presigned URL on another origin, so a plain anchor rather than next/link.
              <a
                href={source.download_url}
                download
                className={buttonClass("secondary", "sm")}
              >
                <Download className="size-3.5" aria-hidden /> Download original
              </a>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft(title);
                setRenaming(true);
              }}
            >
              <Pencil className="size-3.5" aria-hidden /> Rename
            </Button>
            <Button variant="danger" size="sm" onClick={() => setConfirming(true)}>
              <Trash2 className="size-3.5" aria-hidden /> Remove
            </Button>
          </>
        }
      />

      <div className="grid gap-6 px-5 py-6 md:px-8 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          {renaming ? (
            <Panel className="p-4">
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void commitRename();
                }}
              >
                <Label>Rename this source</Label>
                <Input
                  autoFocus
                  value={draft}
                  aria-label="Source title"
                  onChange={(event) => setDraft(event.target.value)}
                  className="mt-2"
                />
                <div className="mt-3 flex gap-2">
                  <Button type="submit" size="sm">
                    Save
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setRenaming(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </form>
            </Panel>
          ) : null}

          <Panel className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <SourceIcon type={source.source_type} />
                <div>
                  <StatusBadge status={source.status} />
                  <p className="mt-1.5 text-[13px] text-muted-foreground">
                    {statusCopy[source.status]?.hint}
                  </p>
                </div>
              </div>
              {source.status === "ready" ? (
                <span className="text-[13px] text-muted-foreground">
                  {source.passage_count} passages indexed
                </span>
              ) : null}
            </div>

            {working ? (
              <div className="mt-4 max-w-md">
                <ProgressBar
                  value={progressFraction(source.status)}
                  label={`${title} — ${statusCopy[source.status]?.label ?? "Working on it"}`}
                />
              </div>
            ) : null}

            {source.status === "failed" ? (
              <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/5 p-3">
                <p className="text-[13px] font-medium text-destructive">
                  {source.error_message ?? "Something went wrong while preparing this source."}
                </p>
                <Button variant="secondary" size="sm" className="mt-3" onClick={() => void retry()}>
                  <RefreshCw className="size-3.5" aria-hidden /> Retry without re-uploading
                </Button>
              </div>
            ) : null}
          </Panel>

          <ActivityTimeline events={events} source={source} />
        </div>

        <div className="space-y-6">
          <Panel className="p-5">
            <Label>Details</Label>
            <dl className="mt-3 space-y-2.5 text-[14px]">
              {metadata.map(([key, value]) => (
                <div key={key} className="flex justify-between gap-4">
                  <dt className="text-muted-foreground capitalize">{key.replace(/_/g, " ")}</dt>
                  <dd className="text-right font-medium">{String(value)}</dd>
                </div>
              ))}
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Cited by</dt>
                <dd className="text-right font-medium">
                  {typeCopy[source.source_type]?.locator ?? "position"}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Passages</dt>
                <dd className="text-right font-medium">{source.passage_count || "—"}</dd>
              </div>
            </dl>
            {source.transcript_url ? (
              <a
                href={source.transcript_url}
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-flex text-[13px] font-medium text-primary hover:underline"
              >
                Read the full transcript
              </a>
            ) : null}
          </Panel>

          <Panel className="p-5">
            <Label>Answers that cited this</Label>
            {cited.length === 0 ? (
              <p className="mt-3 text-[13px] text-muted-foreground">
                Nothing has cited this source yet. Once an answer draws on it, the conversation
                will appear here.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {cited.map((citation, index) => (
                  <li key={`${citation.conversation_id}-${index}`}>
                    <Link
                      href={`/c/${citation.conversation_id}`}
                      className="block rounded-md border border-border p-3 hover:border-border-strong"
                    >
                      <span className="line-clamp-2 text-[13px] font-semibold">
                        {citation.conversation_title}
                      </span>
                      <span className="mt-1.5 flex items-center gap-2">
                        <Pill>{formatLocator(citation.locator)}</Pill>
                        {citation.score !== null ? (
                          <span className="text-[12px] text-muted-foreground">
                            {Math.round(citation.score * 100)}% relevance
                          </span>
                        ) : null}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      {confirming ? (
        <ConfirmDialog
          title="Remove this source?"
          body={`“${title}” and everything indexed from it will be deleted. This can't be undone.`}
          confirmLabel="Remove source"
          busy={deleting}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setConfirming(false)}
        />
      ) : null}
    </div>
  );
}
