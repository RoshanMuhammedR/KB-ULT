"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Logo } from "@kb/ui";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

const WEBSITE_URL = process.env.NEXT_PUBLIC_WEBSITE_URL ?? "";

type Failure = "expired" | "unreachable";

// Landing point of the cross-domain handoff: redeem the single-use ?code for a session
// (cookie set on THIS tenant domain), then drop the user into the app.
function Bootstrap() {
  const params = useSearchParams();
  const router = useRouter();
  const { completeHandoff } = useAuth();
  const [failed, setFailed] = useState<Failure | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // guard React 18 StrictMode double-invoke (code is single-use)
    ran.current = true;

    const code = params.get("code");
    const remember = params.get("remember") === "1";
    if (!code) {
      setFailed("expired");
      return;
    }
    completeHandoff(code, remember)
      .then(() => router.replace("/"))
      .catch((err) => {
        // A real server rejection (ApiError) means the code was expired/used. A network-level
        // failure means this host is unreachable or blocked by CORS — usually a domain that
        // isn't a mapped .test workspace.
        setFailed(err instanceof ApiError ? "expired" : "unreachable");
      });
  }, [params, completeHandoff, router]);

  return (
    <div className="auth__center">
      <div className="bootstrap">
        <Logo />
        {failed ? (
          <>
            {failed === "unreachable" ? (
              <>
                <h1>Couldn&apos;t reach this workspace</h1>
                <p>
                  <code>{typeof window !== "undefined" ? window.location.host : ""}</code> isn&apos;t
                  a recognized workspace address. Make sure it&apos;s a mapped <code>.test</code>{" "}
                  domain — run <code>pnpm run domains:map</code> and register a domain like{" "}
                  <code>acme.test</code>.
                </p>
              </>
            ) : (
              <>
                <h1>This sign-in link has expired</h1>
                <p>
                  Handoff links are single-use and only valid for a minute. Please sign in from your
                  workspace.
                </p>
              </>
            )}
            <a className="saga-btn saga-btn--primary" href="/login">
              Go to sign in
            </a>
            {WEBSITE_URL ? (
              <p className="auth__foot">
                Need a new workspace? <a href={`${WEBSITE_URL}/register`}>Create one</a>
              </p>
            ) : null}
          </>
        ) : (
          <>
            <div className="spinner" />
            <h1>Setting up your workspace…</h1>
            <p>One moment while we sign you in.</p>
          </>
        )}
      </div>
    </div>
  );
}

export default function BootstrapPage() {
  return (
    <Suspense
      fallback={
        <div className="auth__center">
          <div className="spinner" />
        </div>
      }
    >
      <Bootstrap />
    </Suspense>
  );
}
