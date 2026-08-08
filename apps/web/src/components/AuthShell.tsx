import type { ReactNode } from "react";
import { Logo, StatusDot } from "@kb/ui";

// The marketing site is a separate app. In production it is `/` on this same origin (Caddy
// routes /app/* here and /* there); in dev it runs on its own port.
const WEBSITE_URL = process.env.NEXT_PUBLIC_WEBSITE_URL ?? "/";

/** Two-pane auth layout: an editorial aside on the left, the form panel on the right. */
export function AuthShell({
  asideTitle,
  asideSub,
  children
}: {
  asideTitle: string;
  asideSub: string;
  children: ReactNode;
}) {
  return (
    <div className="auth">
      <aside className="auth__aside">
        {/* A plain anchor, not next/link: this leaves the basePath'd app entirely. */}
        <a href={WEBSITE_URL} aria-label="Saga home">
          <Logo />
        </a>
        <div>
          <h2 className="auth__aside-title">{asideTitle}</h2>
          <p className="auth__aside-sub">{asideSub}</p>
        </div>
        <span className="saga-pill">
          <StatusDot tone="live" />
          Private · Source-cited
        </span>
      </aside>
      <section className="auth__panel">{children}</section>
    </div>
  );
}
