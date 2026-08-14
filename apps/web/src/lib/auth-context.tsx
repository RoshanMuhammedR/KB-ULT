"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Session, TokenResponse } from "@/types/api";
import { clearSession, getSession, saveSession } from "@/lib/auth";
import * as api from "@/lib/api";

type Status = "loading" | "authed" | "anon";

type AuthValue = {
  session: Session | null;
  status: Status;
  login: (email: string, password: string, remember: boolean) => Promise<void>;
  /** Create the account and sign straight in. */
  register: (email: string, password: string, remember: boolean) => Promise<void>;
  /** Sign in (or register) from a Google ID token — same session path as the others. */
  loginWithGoogle: (idToken: string, remember: boolean) => Promise<void>;
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
    // Refresh the display profile in the background (name/email may have changed).
    if (s) {
      api
        .getMe()
        .then((me) => {
          const next: Session = { ...s, email: me.email, name: me.name };
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
      name: "",
      expiresAt: Date.now() + tokens.expires_in * 1000,
      remember
    };
    saveSession(base); // so the /auth/me bearer call is authenticated
    let full = base;
    try {
      const me = await api.getMe();
      full = { ...base, email: me.email, name: me.name };
      saveSession(full);
    } catch {
      // Keep the base session even if profile hydration fails — tokens are still valid.
    }
    setSession(full);
    setStatus("authed");
  }, []);

  const login = useCallback(
    async (email: string, password: string, remember: boolean) => {
      const tokens = await api.login({ email: email.trim().toLowerCase(), password });
      await establish(tokens, remember);
    },
    [establish]
  );

  const register = useCallback(
    async (email: string, password: string, remember: boolean) => {
      const tokens = await api.register({ email: email.trim().toLowerCase(), password });
      await establish(tokens, remember);
    },
    [establish]
  );

  const loginWithGoogle = useCallback(
    async (idToken: string, remember: boolean) => {
      const tokens = await api.signInWithGoogle(idToken);
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
    () => ({ session, status, login, register, loginWithGoogle, logout }),
    [session, status, login, register, loginWithGoogle, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

// Client-side route guard. The cookie isn't checked by Next middleware here, so the gate
// lives client-side: a quiet placeholder during hydration, a redirect to /login when anonymous.
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anon") router.replace("/login");
  }, [status, router]);

  if (status !== "authed") {
    return (
      <div className="flex min-h-dvh items-center justify-center" role="status" aria-live="polite">
        <span className="sr-only">Loading your library…</span>
        <div className="size-5 animate-spin rounded-full border-2 border-border border-t-primary" />
      </div>
    );
  }
  return <>{children}</>;
}
