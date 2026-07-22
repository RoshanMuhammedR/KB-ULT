"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Download, RotateCcw, Trash2 } from "lucide-react";
import { buttonClass } from "@kb/ui";
import type { JobEvent, KnowledgeAsset } from "@/types/api";
import {
  deleteAsset,
  getAsset,
  getAssetEvents,
  renameAsset,
  retryAsset
} from "@/lib/api";
import { isProcessing, isTerminal, progressForStatus, stageLabel } from "@/lib/progress";
import { RequireAuth } from "@/lib/auth-context";
import { useToast } from "@/lib/toast";
import { TopBar } from "@/components/TopBar";
import { StatusBadge } from "@/components/StatusBadge";
import { ProgressBar } from "@/components/ProgressBar";

const POLL_INTERVAL_MS = 2000;

function formatTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function renderMetaValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function AssetDetail({ id }: { id: string }) {
  const toast = useToast();
  const router = useRouter();
  const [asset, setAsset] = useState<KnowledgeAsset | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadEvents = useCallback(async () => {
    try {
      setEvents(await getAssetEvents(id));
    } catch {
      // Timeline is best-effort; keep the page usable if events fail to load.
    }
  }, [id]);

  const load = useCallback(async () => {
    try {
      const next = await getAsset(id);
      setAsset(next);
      void loadEvents();
      // Keep polling while the worker is still processing this source.
      if (isProcessing(next.status)) {
        pollTimer.current = setTimeout(() => void load(), POLL_INTERVAL_MS);
      }
    } catch {
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [id, loadEvents]);

  useEffect(() => {
    void load();
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [load]);

  async function onRename(title: string) {
    if (!asset) return;
    const next = title.trim();
    if (!next || next === (asset.title ?? asset.filename)) return;
    try {
      setAsset(await renameAsset(asset.id, next));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Rename failed");
    }
  }

  async function onRetry() {
    if (!asset) return;
    try {
      setAsset(await retryAsset(asset.id));
      if (pollTimer.current) clearTimeout(pollTimer.current);
      pollTimer.current = setTimeout(() => void load(), POLL_INTERVAL_MS);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Retry failed");
    }
  }

  async function onDelete() {
    if (!asset) return;
    try {
      await deleteAsset(asset.id);
      toast.success("Source deleted");
      router.replace("/");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const metaEntries = asset ? Object.entries(asset.metadata ?? {}) : [];

  return (
    <div className="page">
      <TopBar />
      <div className="page-body">
        <Link href="/" className="back-link">
          <ArrowLeft size={14} strokeWidth={1.5} /> Back to library
        </Link>

        {loading ? (
          <div className="rail-empty">Loading source…</div>
        ) : notFound || !asset ? (
          <div className="rail-empty">This source doesn&apos;t exist or was deleted.</div>
        ) : (
          <>
            <div className="page-head">
              <div style={{ flex: 1, minWidth: 0 }}>
                <input
                  className="source__title"
                  style={{ fontSize: 28, marginInlineStart: 0 }}
                  defaultValue={asset.title ?? asset.filename}
                  aria-label="Source title (edit to rename)"
                  onBlur={(e) => void onRename(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  }}
                />
                <div style={{ marginTop: 10 }}>
                  <StatusBadge status={asset.status} />
                </div>
              </div>
            </div>

            {isProcessing(asset.status) ? (
              <div style={{ marginBottom: 20 }}>
                <div className="source__stage">
                  <span>{stageLabel(asset.status)}…</span>
                </div>
                <ProgressBar pct={progressForStatus(asset.status)} active />
              </div>
            ) : null}

            {asset.status === "failed" && asset.error_message ? (
              <div className="source__error" style={{ marginBottom: 20 }}>
                {asset.error_message}
              </div>
            ) : null}

            <div className="detail__grid">
              <div>
                <div className="detail__panel">
                  <h2>Overview</h2>
                  <div className="kv">
                    <span className="kv__k">Type</span>
                    <span className="kv__v">{asset.source_type}</span>
                  </div>
                  <div className="kv">
                    <span className="kv__k">Filename</span>
                    <span className="kv__v">{asset.filename}</span>
                  </div>
                  <div className="kv">
                    <span className="kv__k">Version</span>
                    <span className="kv__v">v{asset.version}</span>
                  </div>
                  <div className="kv">
                    <span className="kv__k">Added</span>
                    <span className="kv__v">{formatTime(asset.created_at)}</span>
                  </div>
                  <div className="kv">
                    <span className="kv__k">Updated</span>
                    <span className="kv__v">{formatTime(asset.updated_at)}</span>
                  </div>

                  {asset.job ? (
                    <>
                      <div className="kv">
                        <span className="kv__k">Job status</span>
                        <span className="kv__v">{asset.job.status}</span>
                      </div>
                      <div className="kv">
                        <span className="kv__k">Attempts</span>
                        <span className="kv__v">
                          attempt {asset.job.attempts} of {asset.job.max_attempts}
                        </span>
                      </div>
                      {asset.job.last_error ? (
                        <div className="kv">
                          <span className="kv__k">Last error</span>
                          <span className="kv__v">{asset.job.last_error}</span>
                        </div>
                      ) : null}
                    </>
                  ) : null}

                  <div className="detail__actions">
                    {asset.status === "failed" ? (
                      <button className={buttonClass({ variant: "ghost", size: "sm" })} onClick={() => void onRetry()}>
                        <RotateCcw size={14} strokeWidth={1.5} /> Retry
                      </button>
                    ) : null}
                    {asset.download_url ? (
                      <a
                        className={buttonClass({ variant: "ghost", size: "sm" })}
                        href={asset.download_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <Download size={14} strokeWidth={1.5} /> Download
                      </a>
                    ) : null}
                    <button className={buttonClass({ variant: "ghost", size: "sm" })} onClick={() => void onDelete()}>
                      <Trash2 size={14} strokeWidth={1.5} /> Delete
                    </button>
                  </div>
                </div>

                {metaEntries.length > 0 ? (
                  <div className="detail__panel" style={{ marginTop: 20 }}>
                    <h2>Details</h2>
                    {metaEntries.map(([k, v]) => (
                      <div className="kv" key={k}>
                        <span className="kv__k">{k}</span>
                        <span className="kv__v">{renderMetaValue(v)}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="detail__panel">
                <h2>Worker log</h2>
                {events.length === 0 ? (
                  <div className="rail-empty" style={{ border: 0 }}>
                    No events recorded yet.
                  </div>
                ) : (
                  <div className="timeline">
                    {events.map((event) => (
                      <div className="timeline__item" key={event.id}>
                        <div className="timeline__rail">
                          <span className={`timeline__dot timeline__dot--${event.level}`} />
                          <span className="timeline__line" />
                        </div>
                        <div className="timeline__body">
                          <span className="timeline__ev">{event.event}</span>
                          <span className="timeline__meta">
                            <span>{event.level}</span>
                            <span>{formatTime(event.ts)}</span>
                          </span>
                          {event.message ? (
                            <span className="timeline__msg">{event.message}</span>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function AssetDetailPage() {
  const params = useParams<{ id: string }>();
  return (
    <RequireAuth>
      <AssetDetail id={params.id} />
    </RequireAuth>
  );
}
