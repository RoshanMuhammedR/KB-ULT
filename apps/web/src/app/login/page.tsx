"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Field, buttonClass } from "@kb/ui";
import { AuthShell } from "@/components/AuthShell";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { status, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "authed") router.replace("/");
  }, [status, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password, remember);
      router.replace("/");
    } catch (err) {
      // The backend returns one generic 401 for every failure by design, so an unknown
      // email and a wrong password read the same here.
      setError(
        err instanceof ApiError && err.status === 401
          ? "Invalid email or password."
          : err instanceof Error
            ? err.message
            : "Sign in failed."
      );
      setBusy(false);
    }
  }

  return (
    <AuthShell
      asideTitle="Cited answers over your own sources."
      asideSub="Upload, process, ask. Every answer shows the passages it came from — private to your workspace."
    >
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
          <Field
            label="Email"
            type="email"
            placeholder="you@example.com"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
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

        <p className="auth__foot">
          No workspace yet? <Link href="/register">Create one</Link>
        </p>
      </form>
    </AuthShell>
  );
}
