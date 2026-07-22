"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import type { JobEvent, JobSummary } from "@/types/api";
import { getAssetEvents, listJobs } from "@/lib/api";
import { RequireAuth } from "@/lib/auth-context";
import { useToast } from "@/lib/toast";
import { TopBar } from "@/components/TopBar";
import { StatusBadge } from "@/components/StatusBadge";

const POLL_INTERVAL_MS = 2000;

function formatTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString();
}

function Activity() {
  const toast = useToast();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);

  const refresh = useCallback(async () => {
    try {
      setJobs(await listJobs());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load jobs");
    }
  }, [toast]);

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
      toast.error(err instanceof Error ? err.message : "Failed to load events");
    }
  }

  return (
    <div className="page">
      <TopBar />
      <div className="page-body">
        <div className="page-head">
          <div>
            <h1>Worker activity</h1>
            <p>Live ingestion jobs and their persisted worker logs.</p>
          </div>
          <button className="icon-btn" title="Refresh" onClick={() => void refresh()}>
            <RefreshCw size={15} strokeWidth={1.5} />
          </button>
        </div>

        <div className="jobs">
          <div className="jobs__head">
            <span />
            <span>Source</span>
            <span>Status</span>
            <span>Attempts</span>
            <span>Started</span>
            <span>Finished</span>
          </div>

          {jobs.length === 0 ? (
            <div className="rail-empty" style={{ border: 0, borderRadius: 0 }}>
              No ingestion jobs yet.
            </div>
          ) : null}

          {jobs.map((job) => (
            <div className="job" key={job.id}>
              <button className="job__row" onClick={() => void toggle(job.asset_id)}>
                <span className="job__caret">
                  {expanded === job.asset_id ? (
                    <ChevronDown size={15} />
                  ) : (
                    <ChevronRight size={15} />
                  )}
                </span>
                <span className="job__file" title={job.filename}>
                  {job.filename}
                </span>
                <span>
                  <StatusBadge status={job.status === "succeeded" ? "ready" : job.status} />
                </span>
                <span className="job__num">
                  {job.attempts}/{job.max_attempts}
                </span>
                <span className="job__num">{formatTime(job.started_at)}</span>
                <span className="job__num">{formatTime(job.finished_at)}</span>
              </button>

              {expanded === job.asset_id ? (
                <div className="job__log">
                  {job.last_error ? <div className="source__error">{job.last_error}</div> : null}
                  {events.length === 0 ? (
                    <div className="rail-empty" style={{ border: 0 }}>
                      No events recorded.
                    </div>
                  ) : null}
                  {events.map((event) => (
                    <div className={`log-line log-line--${event.level}`} key={event.id}>
                      <span className="log-line__t">{formatTime(event.ts)}</span>
                      <span className="log-line__ev">{event.event}</span>
                      <span className="log-line__msg">{event.message ?? ""}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function JobsPage() {
  return (
    <RequireAuth>
      <Activity />
    </RequireAuth>
  );
}
