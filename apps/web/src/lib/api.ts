import type {
  AssetCitation,
  ChatResponse,
  Citation,
  Conversation,
  ConversationSummary,
  JobEvent,
  KnowledgeAsset,
  LoginRequest,
  MeResponse,
  Passage,
  RegisterRequest,
  TokenResponse,
  UploadUrlResponse
} from "@/types/api";
import { clearSession, getAccessToken, getRefreshToken, getSession, saveSession } from "@/lib/auth";

// Same-origin in production (Caddy routes /api/* to FastAPI); an absolute URL in dev, where
// the API runs on its own port.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function readError(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  return (body as { detail?: string }).detail ?? `Request failed with ${response.status}`;
}

// Attempt a single refresh using the rotating refresh token. On success the new
// token pair is persisted and true is returned; on failure the session is cleared.
async function tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  const current = getSession();
  if (!refresh || !current) return false;
  const res = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh })
  });
  if (!res.ok) {
    clearSession();
    return false;
  }
  const tokens = (await res.json()) as TokenResponse;
  saveSession({
    ...current,
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    expiresAt: Date.now() + tokens.expires_in * 1000
  });
  return true;
}

// A hard redirect, so it must carry the basePath itself — unlike next/navigation's router,
// window.location knows nothing about it.
const LOGIN_PATH = "/app/login";

function redirectToLogin(): void {
  // Clear here rather than only in tryRefresh: that one returns early without clearing when
  // there is no refresh token, which used to bounce to /login leaving a dead cookie behind.
  // Clearing also notifies listeners, so in-flight pollers stop before the navigation.
  clearSession();
  if (typeof window !== "undefined" && window.location.pathname !== LOGIN_PATH) {
    window.location.assign(LOGIN_PATH);
  }
}

type ReqOpts = { auth?: boolean; retry?: boolean };

// Central fetch wrapper. Attaches the bearer token, and on a 401 tries one silent
// refresh + retry before bouncing to /login.
async function request<T>(path: string, init: RequestInit = {}, opts: ReqOpts = {}): Promise<T> {
  const { auth = true, retry = true } = opts;
  const headers = new Headers(init.headers);
  if (auth) {
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });

  if (response.status === 401 && auth && retry) {
    if (await tryRefresh()) {
      return request<T>(path, init, { ...opts, retry: false });
    }
    redirectToLogin();
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as Promise<T>;
}

function jsonBody(data: unknown): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
}

// ---- Auth -----------------------------------------------------------------
export function login(data: LoginRequest): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", jsonBody(data), { auth: false });
}
// Creates the account and signs in, in one step; the response is an active session.
export function register(data: RegisterRequest): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/register", jsonBody(data), { auth: false });
}
// Signs in or registers from a Google ID token, returning the same session shape as
// /auth/login — so the caller's token-handling path is identical either way.
export function signInWithGoogle(idToken: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/google", jsonBody({ id_token: idToken }), { auth: false });
}
// The current identity, for the account area. Uses the bearer token + silent refresh.
export function getMe(): Promise<MeResponse> {
  return request<MeResponse>("/auth/me");
}
export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  if (!refresh) return;
  // Best-effort: revoke the refresh-token family server-side; ignore failures.
  await request<void>("/auth/logout", jsonBody({ refresh_token: refresh }), {
    auth: false,
    retry: false
  }).catch(() => undefined);
}

// ---- Documents / sources -------------------------------------------------
export function listAssets(): Promise<KnowledgeAsset[]> {
  return request<KnowledgeAsset[]>("/documents");
}

// Upload in three steps: ask for a signed URL, PUT the file straight to object storage,
// then tell the API it landed. The file never passes through the API process, which is what
// keeps a large source from being bounded by the API container's memory rather than by
// storage. The multipart route below is kept as a fallback for the window where an older
// API is still serving (a deploy in progress), and for anything that cannot reach storage
// directly.
export async function uploadFile(file: File): Promise<KnowledgeAsset> {
  const contentType = file.type || "application/octet-stream";
  let ticket: UploadUrlResponse;
  try {
    ticket = await request<UploadUrlResponse>(
      "/documents/upload-url",
      // Sending the size means an over-limit file is refused now, not after uploading it.
      jsonBody({ filename: file.name, content_type: contentType, size_bytes: file.size })
    );
  } catch (error) {
    // 404/405 means this API doesn't have the endpoint yet. A 400 is a real rejection (an
    // unsupported file type) and must surface as itself rather than being retried a second
    // way that will fail identically.
    if (error instanceof ApiError && (error.status === 404 || error.status === 405)) {
      return uploadFileMultipart(file);
    }
    throw error;
  }

  let put: Response;
  try {
    put = await fetch(ticket.upload_url, {
      method: "PUT",
      // Must match what the URL was signed for, or storage rejects the request.
      headers: { "Content-Type": ticket.content_type },
      body: file
    });
  } catch {
    // fetch only throws (rather than returning a failed response) for network-level
    // problems, and the one that matters here is CORS: the storage bucket has to allow PUT
    // from this origin, which is configuration living outside this repo. Rather than break
    // uploading entirely if that has not been set up, fall back to the route that goes
    // through the API — slower and memory-bound, but it works.
    return uploadFileMultipart(file);
  }
  if (!put.ok) {
    throw new ApiError(put.status, "The file could not be uploaded. Please try again.");
  }

  return request<KnowledgeAsset>(
    `/documents/${ticket.asset_id}/complete`,
    jsonBody({ filename: file.name, content_type: contentType })
  );
}

export function uploadFileMultipart(file: File): Promise<KnowledgeAsset> {
  const formData = new FormData();
  formData.append("file", file);
  return request<KnowledgeAsset>("/documents/upload", { method: "POST", body: formData });
}

export function ingestUrl(url: string): Promise<KnowledgeAsset> {
  return request<KnowledgeAsset>("/documents/ingest-url", jsonBody({ url }));
}

export function getAsset(assetId: string): Promise<KnowledgeAsset> {
  return request<KnowledgeAsset>(`/documents/${assetId}`);
}

export function retryAsset(assetId: string): Promise<KnowledgeAsset> {
  return request<KnowledgeAsset>(`/documents/${assetId}/retry`, { method: "POST" });
}

export function renameAsset(assetId: string, title: string): Promise<KnowledgeAsset> {
  return request<KnowledgeAsset>(`/documents/${assetId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title })
  });
}

export function deleteAsset(assetId: string): Promise<void> {
  return request<void>(`/documents/${assetId}`, { method: "DELETE" });
}

export function getAssetEvents(assetId: string): Promise<JobEvent[]> {
  return request<JobEvent[]>(`/documents/${assetId}/events`);
}

// The cited passage plus its neighbours — the surrounding context the viewer shows.
export function getPassages(assetId: string, around?: number, window = 2): Promise<Passage[]> {
  const query =
    around === undefined ? "" : `?around=${around}&window=${window}`;
  return request<Passage[]>(`/documents/${assetId}/passages${query}`);
}

// Every persisted answer that cited this source.
export function getAssetCitations(assetId: string): Promise<AssetCitation[]> {
  return request<AssetCitation[]>(`/documents/${assetId}/citations`);
}

export function askQuestion(question: string): Promise<ChatResponse> {
  return request<ChatResponse>("/chat/ask", jsonBody({ question }));
}

// ---- Conversations -------------------------------------------------------
export function listConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>("/conversations");
}

export function getConversation(conversationId: string): Promise<Conversation> {
  return request<Conversation>(`/conversations/${conversationId}`);
}

export function renameConversation(conversationId: string, title: string): Promise<Conversation> {
  return request<Conversation>(`/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title })
  });
}

export function deleteConversation(conversationId: string): Promise<void> {
  return request<void>(`/conversations/${conversationId}`, { method: "DELETE" });
}

export function deleteMessage(conversationId: string, messageId: string): Promise<void> {
  return request<void>(`/conversations/${conversationId}/messages/${messageId}`, {
    method: "DELETE"
  });
}

/** The events `streamAnswer` reports back, mirroring the server's SSE event names. */
export type StreamHandlers = {
  onConversation?: (conversation: { id: string; title: string }) => void;
  onDelta?: (text: string) => void;
  onCitations?: (citations: Citation[]) => void;
  onDone?: (done: { message_id: string; insufficient_context: boolean }) => void;
};

/**
 * Ask a question and consume the answer as it streams.
 *
 * The shared `request()` wrapper parses JSON and returns once, which is exactly wrong for a
 * stream, so this is its sibling: same bearer token, same one-shot silent refresh on a 401,
 * same redirect on failure — but it reads the body incrementally and dispatches SSE frames.
 * Pass an AbortSignal so navigating away cancels the request rather than leaking it.
 */
export async function streamAnswer(
  conversationId: string | null,
  question: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
  retry = true
): Promise<void> {
  const target = conversationId ?? "new";
  const headers = new Headers({ "Content-Type": "application/json", Accept: "text/event-stream" });
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_URL}/conversations/${target}/messages`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question }),
    cache: "no-store",
    signal
  });

  if (response.status === 401 && retry) {
    if (await tryRefresh()) {
      return streamAnswer(conversationId, question, handlers, signal, false);
    }
    redirectToLogin();
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  if (!response.body) {
    throw new ApiError(0, "This browser can't stream answers.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  let finished = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // Normalise line endings first: SSE permits \r\n, and a proxy that rewrites them
      // would otherwise stop the frame split below from ever matching.
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      // SSE frames are separated by a blank line; the last piece may be incomplete.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        dispatchFrame(frame, handlers);
      }
    }
    if (buffer.trim()) dispatchFrame(buffer, handlers);
    finished = true;
  } finally {
    // An error frame throws out of the loop above, which leaves the body un-consumed;
    // cancel it so the connection is released rather than left dangling.
    if (!finished) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function dispatchFrame(frame: string, handlers: StreamHandlers): void {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return;

  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return; // A partial or malformed frame is skipped rather than killing the stream.
  }

  switch (event) {
    case "conversation":
      handlers.onConversation?.(payload as { id: string; title: string });
      break;
    case "delta":
      handlers.onDelta?.(String(payload));
      break;
    case "citations":
      handlers.onCitations?.(payload as Citation[]);
      break;
    case "done":
      handlers.onDone?.(payload as { message_id: string; insufficient_context: boolean });
      break;
    case "error":
      throw new ApiError(500, (payload as { message: string }).message);
  }
}

export { ApiError };
