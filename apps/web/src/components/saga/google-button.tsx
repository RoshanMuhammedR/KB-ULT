"use client";

import { useEffect, useRef, useState } from "react";
import { Divider } from "@kb/ui";

const GSI_SRC = "https://accounts.google.com/gsi/client";
const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";

type GoogleAccounts = {
  accounts: {
    id: {
      initialize: (config: {
        client_id: string;
        callback: (response: { credential?: string }) => void;
      }) => void;
      renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
    };
  };
};

declare global {
  interface Window {
    google?: GoogleAccounts;
  }
}

function loadGsi(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.google?.accounts?.id) return Promise.resolve();

  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("script failed")));
      return;
    }
    const script = document.createElement("script");
    script.src = GSI_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("script failed"));
    document.head.appendChild(script);
  });
}

/**
 * Google Identity Services' own button, which hands back a signed ID token the API verifies.
 *
 * Renders nothing at all when NEXT_PUBLIC_GOOGLE_CLIENT_ID is unset, so a developer without
 * Google credentials sees an ordinary email + password form rather than a dead button. This
 * is the only third-party script in the product, and it loads on these two screens only.
 */
export function GoogleButton({
  onCredential,
  disabled
}: {
  onCredential: (idToken: string) => void;
  disabled?: boolean;
}) {
  const holder = useRef<HTMLDivElement | null>(null);
  const [failed, setFailed] = useState(false);
  // Kept in a ref so re-renders don't re-initialise GSI with a stale callback.
  const callback = useRef(onCredential);
  callback.current = onCredential;

  useEffect(() => {
    if (!CLIENT_ID) return;
    let cancelled = false;

    loadGsi()
      .then(() => {
        if (cancelled || !holder.current || !window.google) return;
        window.google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (response) => {
            if (response.credential) callback.current(response.credential);
          }
        });
        window.google.accounts.id.renderButton(holder.current, {
          theme: "outline",
          size: "large",
          width: 320,
          text: "continue_with",
          logo_alignment: "center"
        });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!CLIENT_ID) return null;

  return (
    <div className="space-y-4">
      {failed ? (
        <p className="text-[13px] text-muted-foreground">
          Google sign-in couldn&apos;t load. Use your email and password below.
        </p>
      ) : (
        <div
          ref={holder}
          className={disabled ? "pointer-events-none opacity-50" : undefined}
          aria-busy={disabled}
        />
      )}
      <div className="flex items-center gap-3">
        <Divider className="flex-1" />
        <span className="text-[12px] text-muted-foreground">or</span>
        <Divider className="flex-1" />
      </div>
    </div>
  );
}
