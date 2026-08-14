import { AudioLines, FileCode2, FileText, Presentation, Youtube } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { SourceStatus, SourceType } from "@kb/shared";
import { statusCopy } from "@kb/shared";
import { cn } from "../cn";

export const sourceIcons: Record<SourceType, LucideIcon> = {
  pdf: FileText,
  youtube: Youtube,
  markdown: FileCode2,
  pptx: Presentation,
  audio: AudioLines
};

const sourceTints: Record<SourceType, string> = {
  pdf: "bg-stage-reading/25 text-foreground",
  youtube: "bg-stage-queued/30 text-foreground",
  markdown: "bg-stage-indexing/30 text-foreground",
  pptx: "bg-stage-splitting/30 text-foreground",
  audio: "bg-stage-ready/25 text-foreground"
};

export function SourceIcon({ type, className }: { type: SourceType; className?: string }) {
  const Icon = sourceIcons[type] ?? FileText;
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-9 shrink-0 items-center justify-center rounded-md",
        sourceTints[type] ?? sourceTints.pdf,
        className
      )}
    >
      <Icon className="size-[18px]" strokeWidth={1.75} />
    </span>
  );
}

/** Status is never conveyed by colour alone — shape + text always accompany it. */
export function StatusBadge({ status, className }: { status: SourceStatus; className?: string }) {
  const copy = statusCopy[status] ?? statusCopy.queued;
  const dot = {
    pending: "bg-muted-soft",
    active: "bg-stage-reading",
    ready: "bg-success",
    failed: "bg-destructive"
  }[copy.tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border bg-card px-2.5 py-1 text-[12px] font-medium",
        copy.tone === "failed" && "border-destructive/40 text-destructive",
        className
      )}
    >
      <span
        aria-hidden
        className={cn("size-1.5 rounded-full", dot, copy.tone === "active" && "animate-pulse")}
      />
      {copy.label}
    </span>
  );
}

/** `value` is a fraction, 0–1. */
export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
    >
      <div
        className="h-full rounded-full bg-primary transition-[width] duration-700"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
