// Client-side session storage — a host-scoped cookie (readable by JS; the API auth is still
// bearer, so we read the token out to set the Authorization header). A cookie (not
// localStorage) is what lets "remember me" choose between a persistent cookie and a session
// cookie that dies with the browser.
import type { Session } from "@/types/api";

const KEY = "saga.session";
// Persistent ("remember me") cookies live as long as the refresh token could (~30 days).
const REMEMBER_MAX_AGE = 30 * 24 * 60 * 60;

function writeCookie(value: string, maxAgeSeconds: number | null): void {
  const secure = typeof window !== "undefined" && window.location.protocol === "https:";
  let cookie = `${KEY}=${value}; Path=/; SameSite=Lax`;
  if (maxAgeSeconds !== null) cookie += `; Max-Age=${maxAgeSeconds}`;
  if (secure) cookie += "; Secure";
  document.cookie = cookie;
}

type SessionListener = (session: Session | null) => void;

const listeners = new Set<SessionListener>();

/**
 * Watch the session for changes. The cookie is the source of truth, so this is how React
 * finds out about writes it did not initiate — most importantly the silent token refresh in
 * `api.tryRefresh`, which no component calls and no component could otherwise observe.
 *
 * Deliberately lives here rather than in a store: this module imports nothing, so anything
 * may depend on it without risking an import cycle.
 */
export function subscribeToSession(listener: SessionListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(session: Session | null): void {
  // Copy first — a listener that unsubscribes itself would mutate the set mid-iteration.
  for (const listener of [...listeners]) listener(session);
}

export function saveSession(s: Session): void {
  if (typeof document === "undefined") return;
  const encoded = encodeURIComponent(JSON.stringify(s));
  // Persistent cookie when "remember me"; otherwise a session cookie (no Max-Age).
  writeCookie(encoded, s.remember ? REMEMBER_MAX_AGE : null);
  notify(s);
}

export function getSession(): Session | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${KEY}=`));
  if (!match) return null;
  const raw = decodeURIComponent(match.slice(KEY.length + 1));
  try {
    return JSON.parse(raw) as Session;
  } catch {
    clearSession();
    return null;
  }
}

export function clearSession(): void {
  if (typeof document === "undefined") return;
  writeCookie("", 0);
  notify(null);
}

export function getAccessToken(): string | null {
  return getSession()?.accessToken ?? null;
}

export function getRefreshToken(): string | null {
  return getSession()?.refreshToken ?? null;
}
