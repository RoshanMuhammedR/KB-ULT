"use client";

import { useState } from "react";
import Link from "next/link";
import { Field, buttonClass } from "@kb/ui";
import { AuthShell } from "@/components/AuthShell";
import { productLoginUrl } from "@/lib/config";

/**
 * Domain-picker only. Login credentials are never collected here — the marketing site can't
 * prove which workspace you belong to. We just route you to your workspace's own login page,
 * where the backend enforces that the login happens from the matching domain.
 */
export default function LoginDomainPage() {
  const [domain, setDomain] = useState("");
  const [error, setError] = useState<string | null>(null);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const cleanDomain = domain.trim().toLowerCase();
    if (!cleanDomain) return setError("Enter your workspace domain.");
    setError(null);
    window.location.assign(productLoginUrl(cleanDomain));
  }

  return (
    <AuthShell
      asideTitle="Welcome back."
      asideSub="Tell us your workspace and we'll take you to its sign-in page — logins only work from your own workspace domain."
    >
      <form className="auth__form" onSubmit={onSubmit} noValidate>
        <div className="auth__head">
          <h1 className="auth__title">Log in</h1>
          <p className="auth__lede">Which workspace are you signing in to?</p>
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
            required
          />
        </div>

        <button className={buttonClass({ variant: "primary", block: true })}>Continue</button>

        <p className="auth__foot">
          No workspace yet? <Link href="/register">Create one</Link>
        </p>
      </form>
    </AuthShell>
  );
}
