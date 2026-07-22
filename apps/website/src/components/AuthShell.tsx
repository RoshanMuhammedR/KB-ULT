import type { ReactNode } from "react";
import Link from "next/link";
import { Logo, StatusDot } from "@kb/ui";

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
        <Link href="/" aria-label="Saga home">
          <Logo />
        </Link>
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
