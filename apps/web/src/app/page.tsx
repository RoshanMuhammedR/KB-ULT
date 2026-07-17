"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, FileUp, Link2, RefreshCw, RotateCcw, Send, Trash2 } from "lucide-react";
import type { ChatResponse, Locator, KnowledgeAsset } from "@/types/api";
import { TERMINAL_STATUSES } from "@/types/api";
import {
  askQuestion,
  deleteAsset,
  getAsset,
  ingestUrl,
  listAssets,
  renameAsset,
  retryAsset,
  uploadPdf
} from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

function isTerminal(status: string): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status);
}

// Render a citation's source-neutral locator per source. PDF → "page N";
// YouTube → "at m:ss"; anything else falls back to a generic "type value" label.
function formatLocator(locator: Locator | null): string {
  if (!locator || locator.value === null || locator.value === undefined) return "";
  if (locator.type === "page") return `page ${locator.value}`;
  if (locator.type === "timestamp") {
    const total = Number(locator.value);
    if (Number.isNaN(total)) return "";
    const mins = Math.floor(total / 60);
    const secs = Math.floor(total % 60);
    return `at ${mins}:${secs.toString().padStart(2, "0")}`;
  }
  return `${locator.type} ${locator.value}`;
}

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: ChatResponse["citations"];
};

export default function Home() {
  const [assets, setAssets] = useState<KnowledgeAsset[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [ingestingUrl, setIngestingUrl] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function upsertAsset(asset: KnowledgeAsset) {
    setAssets((current) => {
      const others = current.filter((item) => item.id !== asset.id);
      return [asset, ...others];
    });
  }

  async function refreshAssets() {
    setError(null);
    setAssets(await listAssets());
  }

  useEffect(() => {
    refreshAssets().catch((err) => setError(err.message));
  }, []);

  // Ingestion runs asynchronously in the worker, so after upload we poll the asset
  // until it reaches a terminal state (ready/failed) and reflect each stage in the UI.
  async function pollUntilDone(assetId: string) {
    while (true) {
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      try {
        const latest = await getAsset(assetId);
        upsertAsset(latest);
        if (isTerminal(latest.status)) return;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to poll ingestion status");
        return;
      }
    }
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault();
    if (!selectedFile) return;
    setUploading(true);
    setError(null);
    try {
      // Returns immediately with a `queued` asset (HTTP 202); processing happens later.
      const asset = await uploadPdf(selectedFile);
      upsertAsset(asset);
      setSelectedFile(null);
      void pollUntilDone(asset.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleIngestUrl(event: FormEvent) {
    event.preventDefault();
    const trimmed = sourceUrl.trim();
    if (!trimmed) return;
    setIngestingUrl(true);
    setError(null);
    try {
      // Same async contract as upload: returns a queued asset, then we poll it.
      const asset = await ingestUrl(trimmed);
      upsertAsset(asset);
      setSourceUrl("");
      void pollUntilDone(asset.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "URL ingestion failed");
    } finally {
      setIngestingUrl(false);
    }
  }

  async function handleRetry(assetId: string) {
    setError(null);
    try {
      const asset = await retryAsset(assetId);
      upsertAsset(asset);
      void pollUntilDone(asset.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    }
  }

  async function handleAsk(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    setQuestion("");
    setMessages((current) => [...current, { role: "user", content: trimmed }]);
    try {
      const response = await askQuestion(trimmed);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: response.answer,
          citations: response.citations
        }
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat request failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleRename(asset: KnowledgeAsset, title: string) {
    if (!title.trim() || title === asset.title) return;
    const updated = await renameAsset(asset.id, title.trim());
    setAssets((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  }

  async function handleDelete(assetId: string) {
    await deleteAsset(assetId);
    setAssets((current) => current.filter((asset) => asset.id !== assetId));
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <h1>AI Knowledge Base</h1>
          <p>Upload PDFs and query the indexed knowledge base.</p>
        </div>

        <form className="upload" onSubmit={handleUpload}>
          <input
            type="file"
            accept="application/pdf,.pdf"
            onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
          />
          <button className="primary" type="submit" disabled={!selectedFile || uploading}>
            <FileUp size={16} />
            {uploading ? "Ingesting..." : "Upload PDF"}
          </button>
        </form>

        <form className="upload" onSubmit={handleIngestUrl}>
          <input
            type="url"
            value={sourceUrl}
            placeholder="Paste a YouTube URL"
            onChange={(event) => setSourceUrl(event.target.value)}
          />
          <button className="primary" type="submit" disabled={!sourceUrl.trim() || ingestingUrl}>
            <Link2 size={16} />
            {ingestingUrl ? "Ingesting..." : "Add from URL"}
          </button>
        </form>

        <button className="primary" type="button" onClick={() => refreshAssets().catch((err) => setError(err.message))}>
          <RefreshCw size={16} />
          Refresh Assets
        </button>

        {error ? <div className="error">{error}</div> : null}

        <div className="asset-list">
          {assets.map((asset) => (
            <div className="asset-row" key={asset.id}>
              <div className="asset-main">
                <input
                  className="asset-title"
                  defaultValue={asset.title ?? asset.filename}
                  onBlur={(event) => handleRename(asset, event.target.value).catch((err) => setError(err.message))}
                />
                <div className="asset-meta">
                  <span className={asset.status === "failed" ? "status failed" : "status"}>{asset.status}</span>
                  <span>v{asset.version}</span>
                  <span>{asset.filename}</span>
                </div>
                {asset.error_message ? <div className="error">{asset.error_message}</div> : null}
              </div>
              {asset.status === "failed" ? (
                <button
                  className="icon-button"
                  title="Retry ingestion"
                  type="button"
                  onClick={() => handleRetry(asset.id)}
                >
                  <RotateCcw size={16} />
                </button>
              ) : null}
              <button
                className="icon-button"
                title="Delete asset"
                type="button"
                onClick={() => handleDelete(asset.id).catch((err) => setError(err.message))}
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="main">
        <header className="topbar">
          <div>
            <h2>Chat</h2>
            <p>Answers are generated only from retrieved PDF chunks.</p>
          </div>
          <Link className="nav-link" href="/jobs">
            <Activity size={16} />
            Worker Activity
          </Link>
        </header>

        <div className="chat">
          <div className="messages">
            {messages.map((message, index) => (
              <div className={`message ${message.role}`} key={`${message.role}-${index}`}>
                {message.content}
                {message.citations?.length ? (
                  <div className="citations">
                    {message.citations.map((citation) => (
                      <div className="citation" key={citation.chunk_id}>
                        {citation.filename}
                        {formatLocator(citation.locator) ? `, ${formatLocator(citation.locator)}` : ""} · score{" "}
                        {citation.score.toFixed(3)}
                        <br />
                        {citation.excerpt}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          <form className="composer" onSubmit={handleAsk}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a question about the uploaded PDFs"
            />
            <button className="primary" type="submit" disabled={loading || !question.trim()}>
              <Send size={16} />
              {loading ? "Asking..." : "Ask"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
