"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Client-side route guard. The cookie isn't checked by Next middleware here, so the gate
 * lives client-side: a quiet placeholder during hydration, a redirect to /login when
 * anonymous.
 *
 * This is also what makes `logout` able to stay a plain store action — clearing the session
 * flips `status` to "anon" and the effect below does the navigating.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const status = useAuthStore((state) => state.status);
  const router = useRouter();

  useEffect(() => {
    if (status === "anon") router.replace("/login");
  }, [status, router]);

  if (status !== "authed") {
    return (
      <div className="flex min-h-dvh items-center justify-center" role="status" aria-live="polite">
        <span className="sr-only">Loading your library…</span>
        <div className="size-5 animate-spin rounded-full border-2 border-border border-t-primary" />
      </div>
    );
  }
  return <>{children}</>;
}
