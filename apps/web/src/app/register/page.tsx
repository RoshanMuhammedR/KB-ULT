"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Field, buttonClass } from "@kb/ui";
import { AuthShell } from "@/components/AuthShell";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

const MIN_PASSWORD_LENGTH = 8;

export default function RegisterPage() {
  const { status, register } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
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
    setError(null);

    if (!email.includes("@")) return setError("Enter a valid email address.");
    if (password.length < MIN_PASSWORD_LENGTH) {
      return setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
    }

    setBusy(true);
    try {
      // Registration returns an already-signed-in session, so this lands in the app.
      await register(email, password, name.trim() || undefined, remember);
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("That email is already registered. Try signing in instead.");
      } else if (err instanceof ApiError && err.status === 422) {
        setError("Please check your details and try again.");
      } else {
        setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
      }
      setBusy(false);
    }
  }

  return (
    <AuthShell
      asideTitle="Create your Saga workspace."
      asideSub="One isolated, source-cited knowledge base — yours alone. You'll land inside it the moment you're done."
    >
      <form className="auth__form" onSubmit={onSubmit} noValidate>
        <div className="auth__head">
          <h1 className="auth__title">Get started</h1>
          <p className="auth__lede">An email and a password is all it takes.</p>
        </div>

        {error && (
          <p className="auth__error" role="alert">
            {error}
          </p>
        )}

        <div className="auth__fields">
          <Field
            label="Workspace name (optional)"
            placeholder="Acme Research"
            value={name}
            onChange={(e) => setName(e.target.value)}
            hint="What to call your workspace. Defaults to your email name."
          />
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
            placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
            autoComplete="new-password"
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
          {busy ? "Creating workspace…" : "Create workspace"}
        </button>

        <p className="auth__foot">
          Already have a workspace? <Link href="/login">Log in</Link>
        </p>
      </form>
    </AuthShell>
  );
}
