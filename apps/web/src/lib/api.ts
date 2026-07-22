import type {
  ChatResponse,
  JobEvent,
  JobSummary,
  KnowledgeAsset,
  LoginRequest,
  MeResponse,
  TokenResponse
} from "@/types/api";
import { clearSession, getAccessToken, getRefreshToken, getSession, saveSession } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

function redirectToLogin(): void {
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.assign("/login");
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
// Redeem a single-use cross-domain handoff code (issued on the marketing site) for a session.
export function exchangeHandoff(code: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/handoff/exchange", jsonBody({ code }), { auth: false });
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

export function uploadFile(file: File): Promise<KnowledgeAsset> {
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

export function listJobs(): Promise<JobSummary[]> {
  return request<JobSummary[]>("/jobs");
}

export function getAssetEvents(assetId: string): Promise<JobEvent[]> {
  return request<JobEvent[]>(`/documents/${assetId}/events`);
}

export function askQuestion(question: string): Promise<ChatResponse> {
  return request<ChatResponse>("/chat/ask", jsonBody({ question }));
}

export { ApiError };
