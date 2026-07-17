import type { ChatResponse, JobEvent, JobSummary, KnowledgeAsset } from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed with ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function listAssets(): Promise<KnowledgeAsset[]> {
  return parseResponse<KnowledgeAsset[]>(await fetch(`${API_URL}/documents`, { cache: "no-store" }));
}

export async function uploadPdf(file: File): Promise<KnowledgeAsset> {
  const formData = new FormData();
  formData.append("file", file);
  return parseResponse<KnowledgeAsset>(
    await fetch(`${API_URL}/documents/upload`, {
      method: "POST",
      body: formData
    })
  );
}

// Ingest a URL-based source (e.g. a YouTube video). Returns a queued asset like upload.
export async function ingestUrl(url: string): Promise<KnowledgeAsset> {
  return parseResponse<KnowledgeAsset>(
    await fetch(`${API_URL}/documents/ingest-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    })
  );
}

// Single-asset read used to poll ingestion progress after an upload.
export async function getAsset(assetId: string): Promise<KnowledgeAsset> {
  return parseResponse<KnowledgeAsset>(
    await fetch(`${API_URL}/documents/${assetId}`, { cache: "no-store" })
  );
}

// Re-enqueue a failed asset; the worker re-downloads the source and retries.
export async function retryAsset(assetId: string): Promise<KnowledgeAsset> {
  return parseResponse<KnowledgeAsset>(
    await fetch(`${API_URL}/documents/${assetId}/retry`, { method: "POST" })
  );
}

export async function renameAsset(assetId: string, title: string): Promise<KnowledgeAsset> {
  return parseResponse<KnowledgeAsset>(
    await fetch(`${API_URL}/documents/${assetId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title })
    })
  );
}

export async function deleteAsset(assetId: string): Promise<void> {
  await parseResponse<void>(
    await fetch(`${API_URL}/documents/${assetId}`, {
      method: "DELETE"
    })
  );
}

// Recent ingestion jobs for the /jobs monitoring dashboard.
export async function listJobs(): Promise<JobSummary[]> {
  return parseResponse<JobSummary[]>(await fetch(`${API_URL}/jobs`, { cache: "no-store" }));
}

// The persisted worker-log trail for one asset (all attempts).
export async function getAssetEvents(assetId: string): Promise<JobEvent[]> {
  return parseResponse<JobEvent[]>(
    await fetch(`${API_URL}/documents/${assetId}/events`, { cache: "no-store" })
  );
}

export async function askQuestion(question: string): Promise<ChatResponse> {
  return parseResponse<ChatResponse>(
    await fetch(`${API_URL}/chat/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    })
  );
}
