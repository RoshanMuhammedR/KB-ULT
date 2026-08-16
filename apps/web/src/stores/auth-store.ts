"use client";

import { create } from "zustand";
import type { Session, TokenResponse } from "@/types/api";
import { clearSession, getSession, saveSession } from "@/lib/auth";
import * as api from "@/lib/api";

type Status = "loading" | "authed" | "anon";

type AuthState = {
  session: Session | null;
  status: Status;
  login: (email: string, password: string, remember: boolean) => Promise<void>;
  /** Create the account and sign straight in. */
  register: (email: string, password: string, remember: boolean) => Promise<void>;
  /** Sign in (or register) from a Google ID token — same session path as the others. */
  loginWithGoogle: (idToken: string, remember: boolean) => Promise<void>;
  logout: () => Promise<void>;
};

/**
 * A projection of the session cookie, not a second copy of it.
 *
 * Nothing in here calls `set({ session })`. Every write goes through `saveSession` /
 * `clearSession`, whose notify lands in `session-lifecycle`, which is what puts it in the
 * store. That indirection is the point: it means the silent token refresh inside
 * `api.tryRefresh` — a module no component imports — also updates the UI. Writing `session`
 * directly from here would reintroduce exactly the split-brain this replaced.
 *
 * `logout` deliberately does not navigate: it cannot call `useRouter`, and it does not need
 * to. Clearing flips `status` to "anon", and `RequireAuth` already redirects on that.
 */
export const useAuthStore = create<AuthState>()(() => {
  const establish = async (tokens: TokenResponse, remember: boolean) => {
    const base: Session = {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      email: "",
      name: "",
      expiresAt: Date.now() + tokens.expires_in * 1000,
      remember
    };
    saveSession(base); // so the /auth/me bearer call is authenticated
    try {
      const me = await api.getMe();
      // Re-read rather than spreading `base`: getMe() can 401 and trigger a silent refresh,
      // which rewrites the tokens. Spreading the pre-await snapshot would put the dead pair
      // back and sign the user out on their next request.
      const current = getSession() ?? base;
      saveSession({ ...current, email: me.email, name: me.name });
    } catch {
      // Keep the base session even if profile hydration fails — tokens are still valid.
    }
  };

  return {
    session: null,
    status: "loading",

    login: async (email, password, remember) => {
      const tokens = await api.login({ email: email.trim().toLowerCase(), password });
      await establish(tokens, remember);
    },

    register: async (email, password, remember) => {
      const tokens = await api.register({ email: email.trim().toLowerCase(), password });
      await establish(tokens, remember);
    },

    loginWithGoogle: async (idToken, remember) => {
      const tokens = await api.signInWithGoogle(idToken);
      await establish(tokens, remember);
    },

    logout: async () => {
      await api.logout();
      clearSession();
    }
  };
});
