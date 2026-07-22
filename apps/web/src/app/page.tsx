"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Copy, FileStack, Loader2, MessageSquareText, Search, Send } from "lucide-react";
import { buttonClass } from "@kb/ui";
import type { ChatResponse, KnowledgeAsset } from "@/types/api";
import {
  askQuestion,
  deleteAsset,
  getAsset,
  ingestUrl,
  listAssets,
  renameAsset,
  retryAsset,
  uploadFile
} from "@/lib/api";
import { isProcessing, isTerminal, progressForStatus, stageLabel } from "@/lib/progress";
import { RequireAuth } from "@/lib/auth-context";
import { useToast } from "@/lib/toast";
import { TopBar } from "@/components/TopBar";
import { AddSource } from "@/components/AddSource";
import { StatTiles } from "@/components/StatTiles";
import { SourceCard } from "@/components/SourceCard";
import { ProgressBar } from "@/components/ProgressBar";
import { CitationCard } from "@/components/CitationCard";

const POLL_INTERVAL_MS = 2000;

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: ChatResponse["citations"];
  insufficient?: boolean;
};

type StatusFilter = "all" | "ready" | "processing" | "failed";

function Workspace() {
  const toast = useToast();
  const [assets, setAssets] = useState<KnowledgeAsset[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [busy, setBusy] = useState(false);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);

  function upsertAsset(asset: KnowledgeAsset) {
    setAssets((current) => [asset, ...current.filter((item) => item.id !== asset.id)]);
  }

  async function refreshAssets() {
    try {
      setAssets(await listAssets());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load sources");
    }
  }

  useEffect(() => {
    void refreshAssets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll chat to the newest message.
  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, asking]);

  // Ingestion runs in the worker; poll the asset until it reaches a terminal state.
  async function pollUntilDone(assetId: string) {
    while (true) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      try {
        const latest = await getAsset(assetId);
        upsertAsset(latest);
        if (isTerminal(latest.status)) {
          if (latest.status === "ready")
            toast.success(`“${latest.title ?? latest.filename}” is ready`);
          return;
        }
      } catch {
        return;
      }
    }
  }

  async function handleUploadFile(file: File) {
    setBusy(true);
    try {
      const asset = await uploadFile(file);
      upsertAsset(asset);
      void pollUntilDone(asset.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleIngestUrl(url: string) {
    setBusy(true);
    try {
      const asset = await ingestUrl(url);
      upsertAsset(asset);
      void pollUntilDone(asset.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not add link");
    } finally {
      setBusy(false);
    }
  }

  async function handleRetry(id: string) {
    try {
      const asset = await retryAsset(id);
      upsertAsset(asset);
      void pollUntilDone(asset.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Retry failed");
    }
  }

  async function handleRename(asset: KnowledgeAsset, title: string) {
    const next = title.trim();
    if (!next || next === (asset.title ?? asset.filename)) return;
    try {
      const updated = await renameAsset(asset.id, next);
      setAssets((cur) => cur.map((a) => (a.id === updated.id ? updated : a)));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Rename failed");
    }
  }

  async function handleDelete(id: string) {
    setAssets((cur) => cur.filter((a) => a.id !== id));
    try {
      await deleteAsset(id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
      void refreshAssets();
    }
  }

  async function handleAsk(e: FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || asking) return;
    setQuestion("");
    setMessages((cur) => [...cur, { role: "user", content: trimmed }]);
    setAsking(true);
    try {
      const res = await askQuestion(trimmed);
      setMessages((cur) => [
        ...cur,
        {
          role: "assistant",
          content: res.answer,
          citations: res.citations,
          insufficient: res.insufficient_context
        }
      ]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Chat request failed");
      setMessages((cur) => [
        ...cur,
        { role: "assistant", content: "Something went wrong answering that. Please try again." }
      ]);
    } finally {
      setAsking(false);
    }
  }

  const processing = useMemo(() => assets.filter((a) => isProcessing(a.status)), [assets]);
  const readyCount = useMemo(() => assets.filter((a) => a.status === "ready").length, [assets]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return assets.filter((a) => {
      const matchesQuery =
        !q ||
        (a.title ?? a.filename).toLowerCase().includes(q) ||
        a.filename.toLowerCase().includes(q);
      const matchesFilter =
        filter === "all" ||
        (filter === "ready" && a.status === "ready") ||
        (filter === "failed" && a.status === "failed") ||
        (filter === "processing" && isProcessing(a.status));
      return matchesQuery && matchesFilter;
    });
  }, [assets, query, filter]);

  const filters: { k: StatusFilter; label: string }[] = [
    { k: "all", label: "All" },
    { k: "ready", label: "Ready" },
    { k: "processing", label: "Processing" },
    { k: "failed", label: "Failed" }
  ];

  return (
    <div className="shell">
      <TopBar />
      <div className="workspace">
        {/* ---- Left rail: library ---- */}
        <aside className="rail">
          <div className="rail-scroll">
            <AddSource onUploadFile={handleUploadFile} onIngestUrl={handleIngestUrl} busy={busy} />

            <StatTiles assets={assets} />

            {processing.length > 0 ? (
              <div className="source" style={{ gap: 14 }}>
                <div className="rail-head">
                  <h3>Processing</h3>
                  <span className="count-pill">{processing.length} active</span>
                </div>
                {processing.map((a) => (
                  <div key={a.id}>
                    <div className="source__stage">
                      <span
                        style={{
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap"
                        }}
                      >
                        {a.title ?? a.filename}
                      </span>
                      <span>{stageLabel(a.status)}</span>
                    </div>
                    <ProgressBar pct={progressForStatus(a.status)} active />
                  </div>
                ))}
              </div>
            ) : null}

            <div className="rail-head">
              <h3>Sources</h3>
              <span className="count-pill">{assets.length}</span>
            </div>

            <div className="search">
              <Search size={15} strokeWidth={1.5} />
              <input
                placeholder="Search sources…"
                aria-label="Search sources"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="chips">
              {filters.map((f) => (
                <button
                  key={f.k}
                  className={`chip${filter === f.k ? " is-on" : ""}`}
                  onClick={() => setFilter(f.k)}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {assets.length === 0 ? (
              <div className="rail-empty">
                No sources yet — add a PDF or paste a link above to get started.
              </div>
            ) : filtered.length === 0 ? (
              <div className="rail-empty">Nothing matches your search.</div>
            ) : (
              filtered.map((a) => (
                <SourceCard
                  key={a.id}
                  asset={a}
                  onRename={handleRename}
                  onRetry={handleRetry}
                  onDelete={handleDelete}
                />
              ))
            )}
          </div>
        </aside>

        {/* ---- Right: chat ---- */}
        <main className="main">
          <div className="chat">
            <div className="messages" ref={messagesRef}>
              {messages.length === 0 ? (
                <div className="empty">
                  <div className="empty__icon">
                    <MessageSquareText size={24} strokeWidth={1.5} />
                  </div>
                  <h3>Ask your knowledge base</h3>
                  <p>
                    {readyCount > 0
                      ? "Ask a question — answers are drawn only from your sources, with citations you can verify."
                      : "Add a source and wait for it to finish processing, then ask anything about it."}
                  </p>
                </div>
              ) : (
                messages.map((m, i) => (
                  <div className={`msg msg--${m.role}`} key={`${m.role}-${i}`}>
                    <span className="msg__role">{m.role === "user" ? "You" : "Saga"}</span>
                    <div className={`msg__bubble${m.insufficient ? " msg__bubble--insufficient" : ""}`}>
                      {m.insufficient ? (
                        <span className="insufficient-tag">Limited context in your sources</span>
                      ) : null}
                      {m.content}
                    </div>
                    {m.citations && m.citations.length > 0 ? (
                      <div className="citations">
                        {m.citations.map((c) => (
                          <CitationCard key={c.chunk_id} citation={c} />
                        ))}
                      </div>
                    ) : null}
                    {m.role === "assistant" && !m.insufficient ? (
                      <div className="msg__tools">
                        <button
                          className={buttonClass({ variant: "ghost", size: "sm" })}
                          onClick={() =>
                            void navigator.clipboard
                              ?.writeText(m.content)
                              .then(() => toast.success("Copied"))
                          }
                        >
                          <Copy size={13} /> Copy
                        </button>
                      </div>
                    ) : null}
                  </div>
                ))
              )}
              {asking ? (
                <div className="msg msg--assistant">
                  <span className="msg__role">Saga</span>
                  <div className="msg__bubble">
                    <div className="thinking">
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            <form className="composer" onSubmit={handleAsk}>
              <textarea
                className="composer__input"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === "Enter")
                    void handleAsk(e as unknown as FormEvent);
                }}
                placeholder="Ask a question about your sources…"
                aria-label="Ask a question"
                rows={1}
              />
              <button
                className={buttonClass({ variant: "primary" })}
                type="submit"
                disabled={asking || !question.trim()}
              >
                {asking ? <Loader2 size={15} className="spin" /> : <Send size={15} />}
                Ask
              </button>
              <span className="composer__hint">
                <FileStack size={12} /> {readyCount} source{readyCount === 1 ? "" : "s"} ready ·
                ⌘/Ctrl+Enter to send
              </span>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <RequireAuth>
      <Workspace />
    </RequireAuth>
  );
}
