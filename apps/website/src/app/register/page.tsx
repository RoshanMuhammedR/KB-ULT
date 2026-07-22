"use client";

import { useState } from "react";
import Link from "next/link";
import { Field, buttonClass } from "@kb/ui";
import { AuthShell } from "@/components/AuthShell";
import { register, issueHandoff, ApiError } from "@/lib/api";
import { productBootstrapUrl } from "@/lib/config";

// A workspace domain must be a real, multi-label hostname (e.g. acme.test). Single-label
// names like "roshan" resolve unpredictably and fail the API's CORS allowlist on handoff.
const DOMAIN_RE =
  /^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;

function isValidDomain(value: string): boolean {
  return DOMAIN_RE.test(value);
}

export default function RegisterPage() {
  const [domain, setDomain] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const cleanDomain = domain.trim().toLowerCase();
    if (!cleanDomain) return setError("Choose a workspace domain.");
    if (!isValidDomain(cleanDomain)) {
      return setError(
        "Use a full domain with a dot, like acme.test — and make sure it's mapped locally (pnpm run domains:map)."
      );
    }
    if (password.length < 8) return setError("Password must be at least 8 characters.");

    setBusy(true);
    try {
      const tokens = await register({
        domain: cleanDomain,
        email: email.trim(),
        password,
        name: name.trim() || undefined
      });
      // Carry the new session to the tenant domain via a single-use handoff code.
      const { code } = await issueHandoff(tokens.access_token);
      window.location.assign(productBootstrapUrl(cleanDomain, code, remember));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("That workspace domain is already taken. Try another.");
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
          <p className="auth__lede">Pick a workspace domain and you're in.</p>
        </div>

        {error && (
          <p className="auth__error" role="alert">
            {error}
          </p>
        )}

        <div className="auth__fields">
          <Field
            label="Workspace domain"
            placeholder="acme.test"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            hint="This becomes your workspace URL. Use letters, numbers, and dots."
            required
          />
          <Field
            label="Name (optional)"
            placeholder="Acme Research"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
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
            placeholder="At least 8 characters"
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
