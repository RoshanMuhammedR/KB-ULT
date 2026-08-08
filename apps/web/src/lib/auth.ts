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

export function saveSession(s: Session): void {
  if (typeof document === "undefined") return;
  const encoded = encodeURIComponent(JSON.stringify(s));
  // Persistent cookie when "remember me"; otherwise a session cookie (no Max-Age).
  writeCookie(encoded, s.remember ? REMEMBER_MAX_AGE : null);
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
}

export function getAccessToken(): string | null {
  return getSession()?.accessToken ?? null;
}

export function getRefreshToken(): string | null {
  return getSession()?.refreshToken ?? null;
}
