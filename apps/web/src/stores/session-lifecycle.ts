"use client";

import { getSession, saveSession, subscribeToSession } from "@/lib/auth";
import * as api from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { useConversationsStore } from "@/stores/conversations-store";
import { useSourcesStore } from "@/stores/sources-store";

let started = false;

/**
 * Wires the session cookie to the stores, and hydrates auth from it.
 *
 * Must run in an effect, never at module scope: it reads the cookie, and doing that during
 * client module evaluation would make the first client render say "authed" while the server
 * HTML said "loading" — a hydration mismatch where today there is none.
 *
 * Idempotent, so StrictMode's double mount is a no-op.
 */
export function initClientStores(): void {
  if (started) return;
  started = true;

  subscribeToSession((session) => {
    const had = useAuthStore.getState().session !== null;
    useAuthStore.setState({ session, status: session ? "authed" : "anon" });

    // Every path that ends a session lands here: the sign-out button, a refresh that failed
    // inside api.tryRefresh, a 401 bounce. Module-scoped stores have no unmount to clean up
    // after them, so this is the only thing standing between a soft sign-out and 2-second
    // poll loops running forever against a dead token.
    if (!session && had) {
      useSourcesStore.getState().reset(); // reset() calls stopAll()
      useConversationsStore.getState().reset();
    }
  });

  const existing = getSession();
  useAuthStore.setState({ session: existing, status: existing ? "authed" : "anon" });

  if (existing) {
    // The display name/email may have changed since this cookie was written. Re-read inside
    // the continuation: getMe() can trigger a silent refresh that rewrote the tokens, and
    // spreading the pre-await snapshot would put the stale pair back.
    api
      .getMe()
      .then((me) => {
        const current = getSession();
        if (current) saveSession({ ...current, email: me.email, name: me.name });
      })
      .catch(() => undefined);
  }
}
