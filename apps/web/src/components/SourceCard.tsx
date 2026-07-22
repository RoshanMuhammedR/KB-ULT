import Link from "next/link";
import { Download, FileText, Maximize2, RotateCcw, Trash2, Youtube } from "lucide-react";
import type { KnowledgeAsset } from "@/types/api";
import { isProcessing, progressForStatus, stageLabel } from "@/lib/progress";
import { ProgressBar } from "./ProgressBar";
import { StatusBadge } from "./StatusBadge";

// Type-extensible: YouTube gets the video glyph, everything else the document glyph.
function SourceIcon({ sourceType }: { sourceType: string }) {
  const isVideo = sourceType === "youtube" || sourceType === "url" || sourceType === "website";
  return (
    <span className="source__icon">
      {isVideo ? <Youtube size={18} strokeWidth={1.5} /> : <FileText size={18} strokeWidth={1.5} />}
    </span>
  );
}

export function SourceCard({
  asset,
  onRename,
  onRetry,
  onDelete
}: {
  asset: KnowledgeAsset;
  onRename: (asset: KnowledgeAsset, title: string) => void;
  onRetry: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const processing = isProcessing(asset.status);
  const failed = asset.status === "failed";

  return (
    <div className="source">
      <div className="source__top">
        <SourceIcon sourceType={asset.source_type} />
        <div className="source__body">
          <input
            className="source__title"
            defaultValue={asset.title ?? asset.filename}
            aria-label="Source title (edit to rename)"
            onBlur={(e) => onRename(asset, e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            }}
          />
          <div className="source__meta">
            <StatusBadge status={asset.status} />
            {asset.version > 1 ? <span>v{asset.version}</span> : null}
            <span className="source__fname" title={asset.filename}>
              {asset.filename}
            </span>
          </div>
        </div>
        <div className="source__actions">
          <Link className="icon-btn" title="View details" href={`/sources/${asset.id}`}>
            <Maximize2 size={14} strokeWidth={1.5} />
          </Link>
          {failed ? (
            <button className="icon-btn" title="Retry ingestion" onClick={() => onRetry(asset.id)}>
              <RotateCcw size={14} strokeWidth={1.5} />
            </button>
          ) : null}
          {asset.download_url ? (
            <a
              className="icon-btn"
              title="Download original"
              href={asset.download_url}
              target="_blank"
              rel="noreferrer"
            >
              <Download size={14} strokeWidth={1.5} />
            </a>
          ) : null}
          <button
            className="icon-btn icon-btn--danger"
            title="Delete source"
            onClick={() => onDelete(asset.id)}
          >
            <Trash2 size={14} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {processing ? (
        <div>
          <div className="source__stage">
            <span>{stageLabel(asset.status)}…</span>
          </div>
          <ProgressBar pct={progressForStatus(asset.status)} active />
        </div>
      ) : null}

      {failed && asset.error_message ? (
        <div className="source__error">{asset.error_message}</div>
      ) : null}
    </div>
  );
}
