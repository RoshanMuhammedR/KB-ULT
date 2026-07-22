"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Session, TokenResponse } from "@/types/api";
import { clearSession, currentDomain, getSession, saveSession } from "@/lib/auth";
import * as api from "@/lib/api";

type Status = "loading" | "authed" | "anon";

type AuthValue = {
  session: Session | null;
  status: Status;
  /** Domain is derived from the host; `domainOverride` is only for plain-localhost dev. */
  login: (
    email: string,
    password: string,
    remember: boolean,
    domainOverride?: string
  ) => Promise<void>;
  /** Redeem a cross-domain handoff code (the /bootstrap page). */
  completeHandoff: (code: string, remember: boolean) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const router = useRouter();

  // Hydrate from the cookie on mount (client-only).
  useEffect(() => {
    const s = getSession();
    setSession(s);
    setStatus(s ? "authed" : "anon");
    // Refresh the display profile in the background (name/email/domain may have changed).
    if (s) {
      api
        .getMe()
        .then((me) => {
          const next: Session = { ...s, email: me.email, domain: me.domain, name: me.name };
          saveSession(next);
          setSession(next);
        })
        .catch(() => undefined);
    }
  }, []);

  // Persist tokens, then resolve the display profile from /auth/me.
  const establish = useCallback(async (tokens: TokenResponse, remember: boolean) => {
    const base: Session = {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      email: "",
      domain: currentDomain(),
      name: "",
      expiresAt: Date.now() + tokens.expires_in * 1000,
      remember
    };
    saveSession(base); // so the /auth/me bearer call is authenticated
    let full = base;
    try {
      const me = await api.getMe();
      full = { ...base, email: me.email, domain: me.domain, name: me.name };
      saveSession(full);
    } catch {
      // Keep the base session even if profile hydration fails — tokens are still valid.
    }
    setSession(full);
    setStatus("authed");
  }, []);

  const login = useCallback(
    async (email: string, password: string, remember: boolean, domainOverride?: string) => {
      const domain = (domainOverride?.trim() || currentDomain()).toLowerCase();
      const tokens = await api.login({ domain, email, password });
      await establish(tokens, remember);
    },
    [establish]
  );

  const completeHandoff = useCallback(
    async (code: string, remember: boolean) => {
      const tokens = await api.exchangeHandoff(code);
      await establish(tokens, remember);
    },
    [establish]
  );

  const logout = useCallback(async () => {
    await api.logout();
    clearSession();
    setSession(null);
    setStatus("anon");
    router.replace("/login");
  }, [router]);

  const value = useMemo(
    () => ({ session, status, login, completeHandoff, logout }),
    [session, status, login, completeHandoff, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

// Client-side route guard. The cookie isn't checked by Next middleware here, so the gate
// lives client-side: a splash during hydration, a redirect to /login when anonymous.
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anon") router.replace("/login");
  }, [status, router]);

  if (status !== "authed") {
    return (
      <div className="splash">
        <div className="spinner" />
      </div>
    );
  }
  return <>{children}</>;
}
