"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Logo, Field, StatusDot, buttonClass } from "@kb/ui";
import { useAuth } from "@/lib/auth-context";
import { currentDomain } from "@/lib/auth";
import { ApiError } from "@/lib/api";

const WEBSITE_URL = process.env.NEXT_PUBLIC_WEBSITE_URL ?? "";

export default function LoginPage() {
  const { status, login } = useAuth();
  const router = useRouter();
  const [domain, setDomain] = useState("");
  const [isLocalhost, setIsLocalhost] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // The workspace is the host you're visiting (e.g. acme.test) — shown, not asked for.
  // On plain localhost there's no tenant host, so we let you type one (dev only).
  useEffect(() => {
    const host = currentDomain();
    setDomain(host);
    setIsLocalhost(host === "");
  }, []);

  useEffect(() => {
    if (status === "authed") router.replace("/");
  }, [status, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password, remember, isLocalhost ? domain.trim() : undefined);
      router.replace("/");
    } catch (err) {
      // The backend returns one generic 401 for every failure by design.
      setError(
        err instanceof ApiError && err.status === 401
          ? "Invalid credentials or inactive account."
          : err instanceof Error
            ? err.message
            : "Sign in failed."
      );
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <aside className="auth__aside">
        <Logo />
        <div>
          <h2 className="auth__aside-title">Cited answers over your own sources.</h2>
          <p className="auth__aside-sub">
            Upload, process, ask. Every answer shows the passages it came from — private to your
            workspace.
          </p>
        </div>
        <span className="saga-pill">
          <StatusDot tone="live" />
          Private · Source-cited
        </span>
      </aside>

      <section className="auth__panel">
        <form className="auth__form" onSubmit={onSubmit} noValidate>
          <div className="auth__head">
            <h1 className="auth__title">Welcome back</h1>
            <p className="auth__lede">Sign in to your workspace.</p>
          </div>

          {error && (
            <p className="auth__error" role="alert">
              {error}
            </p>
          )}

          <div className="auth__fields">
            {isLocalhost ? (
              <Field
                label="Workspace domain (dev)"
                placeholder="acme.test"
                autoCapitalize="none"
                spellCheck={false}
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                hint="On localhost there's no tenant host — type the workspace to sign in to."
                required
              />
            ) : (
              <div className="auth__workspace">
                <span className="auth__workspace-label">Workspace</span>
                <span className="auth__workspace-value">{domain}</span>
              </div>
            )}
            <Field
              label="Email"
              type="email"
              placeholder="you@acme.test"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <Field
              label="Password"
              type="password"
              placeholder="••••••••"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <label className="auth__check">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            Keep me signed in on this device
          </label>

          <button className={buttonClass({ variant: "primary", block: true })} disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>

          {WEBSITE_URL ? (
            <p className="auth__foot">
              No workspace yet? <a href={`${WEBSITE_URL}/register`}>Create one</a>
            </p>
          ) : null}
        </form>
      </section>
    </div>
  );
}
