"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button, Field, Input } from "@kb/ui";
import { AuthShell } from "@/components/saga/auth-shell";
import { GoogleButton } from "@/components/saga/google-button";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { status, login, loginWithGoogle } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "authed") router.replace("/");
  }, [status, router]);

  function describe(err: unknown): string {
    // The backend returns one generic 401 for every failure by design, so an unknown email
    // and a wrong password read the same here.
    if (err instanceof ApiError && err.status === 401) return "Invalid email or password.";
    if (err instanceof ApiError && err.status === 503) {
      return "Google sign-in isn't set up on this server. Use your email and password.";
    }
    return err instanceof Error ? err.message : "Sign in failed.";
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password, remember);
      router.replace("/");
    } catch (err) {
      setError(describe(err));
      setBusy(false);
    }
  }

  async function onGoogle(idToken: string) {
    setBusy(true);
    setError(null);
    try {
      await loginWithGoogle(idToken, remember);
      router.replace("/");
    } catch (err) {
      setError(describe(err));
      setBusy(false);
    }
  }

  return (
    <AuthShell
      asideTitle="Cited answers over your own sources."
      asideSub="Upload, process, ask. Every answer shows the passages it came from — private to you."
    >
      <div className="space-y-6">
        <div>
          <h1 className="text-display-md">Welcome back</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">Sign in to your library.</p>
        </div>

        {error ? (
          <p
            className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[13px] text-destructive"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        <GoogleButton onCredential={(token) => void onGoogle(token)} disabled={busy} />

        <form className="space-y-4" onSubmit={onSubmit} noValidate>
          <Field label="Email" id="email">
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </Field>
          <Field label="Password" id="password">
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </Field>

          <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
              className="size-4 rounded border-border"
            />
            Keep me signed in on this device
          </label>

          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="text-[13px] text-muted-foreground">
          No account yet?{" "}
          <Link href="/register" className="font-medium text-foreground hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </AuthShell>
  );
}
