"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import type { JobEvent, JobSummary } from "@/types/api";
import { getAssetEvents, listJobs } from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

function formatTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString();
}

// Worker Activity dashboard. Procrastinate ships no standalone UI, so this reads our
// domain-owned job + event tables. It polls the job list on an interval (the same
// cadence the upload flow uses) and lazily loads an asset's worker-log trail when a
// row is expanded.
export default function JobsPage() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setJobs(await listJobs());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load jobs");
    }
  }, []);

  // Poll the job list so statuses/attempts update live while workers run.
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  async function toggle(assetId: string) {
    if (expanded === assetId) {
      setExpanded(null);
      return;
    }
    setExpanded(assetId);
    setEvents([]);
    try {
      setEvents(await getAssetEvents(assetId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load events");
    }
  }

  return (
    <main className="jobs-shell">
      <header className="topbar">
        <div>
          <h2>Worker Activity</h2>
          <p>Live ingestion jobs and their persisted worker logs.</p>
        </div>
        <div className="topbar-actions">
          <button className="icon-button" type="button" title="Refresh" onClick={() => void refresh()}>
            <RefreshCw size={16} />
          </button>
          <Link className="nav-link" href="/">
            <ArrowLeft size={16} />
            Back to chat
          </Link>
        </div>
      </header>

      {error ? <div className="error jobs-error">{error}</div> : null}

      <div className="jobs-table">
        <div className="jobs-row jobs-head">
          <span />
          <span>File</span>
          <span>Status</span>
          <span>Attempts</span>
          <span>Started</span>
          <span>Finished</span>
        </div>

        {jobs.length === 0 ? <div className="jobs-empty">No ingestion jobs yet.</div> : null}

        {jobs.map((job) => (
          <div className="jobs-group" key={job.id}>
            <button className="jobs-row jobs-body" type="button" onClick={() => void toggle(job.asset_id)}>
              <span className="jobs-caret">
                {expanded === job.asset_id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </span>
              <span className="jobs-file" title={job.filename}>{job.filename}</span>
              <span>
                <span className={`status ${job.status === "failed" ? "failed" : ""}`}>{job.status}</span>
              </span>
              <span>{job.attempts}/{job.max_attempts}</span>
              <span>{formatTime(job.started_at)}</span>
              <span>{formatTime(job.finished_at)}</span>
            </button>

            {expanded === job.asset_id ? (
              <div className="jobs-log">
                {job.last_error ? <div className="error">{job.last_error}</div> : null}
                {events.length === 0 ? <div className="jobs-empty">No events recorded.</div> : null}
                {events.map((event) => (
                  <div className={`log-line ${event.level === "error" ? "log-error" : ""}`} key={event.id}>
                    <span className="log-time">{formatTime(event.ts)}</span>
                    <span className="log-event">{event.event}</span>
                    <span className="log-message">{event.message ?? ""}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </main>
  );
}
