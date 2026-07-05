import type { ChatResponse, KnowledgeAsset } from "@/types/api";

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

export async function askQuestion(question: string): Promise<ChatResponse> {
  return parseResponse<ChatResponse>(
    await fetch(`${API_URL}/chat/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    })
  );
}
