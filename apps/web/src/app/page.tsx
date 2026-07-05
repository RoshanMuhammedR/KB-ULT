"use client";

import { FormEvent, useEffect, useState } from "react";
import { FileUp, RefreshCw, Send, Trash2 } from "lucide-react";
import type { ChatResponse, KnowledgeAsset } from "@/types/api";
import { askQuestion, deleteAsset, listAssets, renameAsset, uploadPdf } from "@/lib/api";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: ChatResponse["citations"];
};

export default function Home() {
  const [assets, setAssets] = useState<KnowledgeAsset[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refreshAssets() {
    setError(null);
    setAssets(await listAssets());
  }

  useEffect(() => {
    refreshAssets().catch((err) => setError(err.message));
  }, []);

  async function handleUpload(event: FormEvent) {
    event.preventDefault();
    if (!selectedFile) return;
    setUploading(true);
    setError(null);
    try {
      const asset = await uploadPdf(selectedFile);
      setAssets((current) => [asset, ...current.filter((item) => item.id !== asset.id)]);
      setSelectedFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
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
                        {citation.page_number ? `, page ${citation.page_number}` : ""} · score{" "}
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
