"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button, Field, Input } from "@kb/ui";
import { AuthShell } from "@/components/saga/auth-shell";
import { GoogleButton } from "@/components/saga/google-button";
import { useAuthStore } from "@/stores/auth-store";
import { ApiError } from "@/lib/api";

const MIN_PASSWORD_LENGTH = 8;

export default function RegisterPage() {
  const status = useAuthStore((state) => state.status);
  const register = useAuthStore((state) => state.register);
  const loginWithGoogle = useAuthStore((state) => state.loginWithGoogle);
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
    if (err instanceof ApiError && err.status === 409) {
      return "That email is already registered. Sign in instead.";
    }
    if (err instanceof ApiError && err.status === 422) {
      return "Please check your details and try again.";
    }
    if (err instanceof ApiError && err.status === 503) {
      return "Google sign-in isn't set up on this server. Use your email and password.";
    }
    return err instanceof Error ? err.message : "Sign up failed.";
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!email.includes("@")) {
      setError("Enter a valid email address.");
      return;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`);
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await register(email, password, remember);
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
      asideTitle="Answers you can trace back to the page."
      asideSub="Add your documents, recordings and links, then ask questions of them. Every answer comes back with the passages behind it."
    >
      <div className="space-y-6">
        <div>
          <h1 className="text-display-md">Create your account</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Email and password, or Google. No plans to pick.
          </p>
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
          <Field
            label="Password"
            id="password"
            hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          >
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              autoComplete="new-password"
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
            {busy ? "Creating your account…" : "Create account"}
          </Button>
        </form>

        <p className="text-[13px] text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-foreground hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </AuthShell>
  );
}
