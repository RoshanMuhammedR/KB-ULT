"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, MessageSquareText } from "lucide-react";
import { Logo } from "@kb/ui";
import { AccountMenu } from "./AccountMenu";

// Persistent product header: Saga wordmark + primary nav (Chat/Library ↔ Activity) + account.
export function TopBar() {
  const pathname = usePathname();
  const isLibrary = pathname === "/";
  const isActivity = pathname.startsWith("/jobs");
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <Link href="/" aria-label="Saga home">
          <Logo />
        </Link>
        <nav className="app-nav" aria-label="Primary">
          <Link href="/" className="app-nav__link" data-active={isLibrary}>
            <MessageSquareText size={16} strokeWidth={1.5} />
            <span className="only-wide">Chat &amp; Library</span>
          </Link>
          <Link href="/jobs" className="app-nav__link" data-active={isActivity}>
            <Activity size={16} strokeWidth={1.5} />
            <span className="only-wide">Activity</span>
          </Link>
        </nav>
        <div className="app-header__spacer" />
        <AccountMenu />
      </div>
    </header>
  );
}
