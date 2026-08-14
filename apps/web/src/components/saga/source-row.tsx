"use client";

import Link from "next/link";
import { RefreshCw, Trash2 } from "lucide-react";
import {
  progressFraction,
  relative,
  sourceTitle,
  statusCopy,
  typeCopy,
  isProcessing
} from "@kb/shared";
import { Button, Panel, ProgressBar, SourceIcon, StatusBadge } from "@kb/ui";
import type { KnowledgeAsset } from "@/types/api";

/** Recovery advice worth giving, keyed by the step that actually failed. */
function recoveryHint(source: KnowledgeAsset): string {
  if (source.source_type === "pdf") {
    return "Try a version with selectable text, or run it through OCR first.";
  }
  if (source.source_type === "youtube") {
    return "This video may have transcripts disabled. Try one with captions.";
  }
  if (source.source_type === "audio") {
    return "Check the recording has audible speech, then try again.";
  }
  return "Retrying is usually enough — the original file is still stored.";
}

export function SourceRow({
  source,
  onRetry,
  onDelete
}: {
  source: KnowledgeAsset;
  onRetry: (source: KnowledgeAsset) => void;
  onDelete: (source: KnowledgeAsset) => void;
}) {
  const working = isProcessing(source.status);
  const title = sourceTitle(source);

  return (
    <Panel className="p-4">
      <div className="flex flex-wrap items-start gap-4">
        <SourceIcon type={source.source_type} />
        <div className="min-w-0 flex-1">
          <Link
            href={`/sources/${source.id}`}
            className="block truncate text-[15px] font-semibold hover:underline"
          >
            {title}
          </Link>
          <p className="mt-0.5 truncate text-[13px] text-muted-foreground">
            {typeCopy[source.source_type]?.label ?? source.source_type} · {source.filename}
            {source.created_at ? ` · added ${relative(source.created_at)}` : ""}
          </p>

          {working ? (
            <div className="mt-3 max-w-md">
              <ProgressBar
                value={progressFraction(source.status)}
                label={`${title} — ${statusCopy[source.status]?.label ?? "Working on it"}`}
              />
              <p className="mt-1.5 text-[12px] text-muted-foreground">
                {statusCopy[source.status]?.hint}
                {source.source_type === "audio" ? " Recordings take a few minutes." : ""}
              </p>
            </div>
          ) : null}

          {source.status === "failed" ? (
            <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/5 p-3">
              <p className="text-[13px] font-medium text-destructive">
                {source.error_message ?? "Something went wrong while preparing this source."}
              </p>
              <p className="mt-1 text-[12px] text-muted-foreground">{recoveryHint(source)}</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => onRetry(source)}>
                  <RefreshCw className="size-3.5" aria-hidden /> Retry without re-uploading
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onDelete(source)}>
                  <Trash2 className="size-3.5" aria-hidden /> Remove
                </Button>
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex flex-col items-end gap-2">
          <StatusBadge status={source.status} />
          {source.status === "ready" && source.passage_count > 0 ? (
            <span className="text-[12px] text-muted-foreground">
              {source.passage_count} passages
            </span>
          ) : null}
        </div>
      </div>
    </Panel>
  );
}
