"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Library, Menu, MessagesSquare, Moon, Sun, UserRound, X } from "lucide-react";
import { Logo, Pill, cn, useTheme } from "@kb/ui";
import { useAuthStore } from "@/stores/auth-store";
import { useSourcesStore } from "@/stores/sources-store";

const links = [
  { href: "/", label: "Ask", icon: MessagesSquare, exact: true },
  { href: "/library", label: "Library", icon: Library, exact: false },
  { href: "/account", label: "Account", icon: UserRound, exact: false }
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  // A number, not the counts object: an ingestion poll tick that doesn't move this figure
  // now leaves the whole shell — and everything it wraps — untouched.
  const processing = useSourcesStore((state) => state.counts.processing);
  const email = useAuthStore((state) => state.session?.email ?? null);
  const dark = theme === "dark";

  const nav = (
    <nav aria-label="Product" className="flex flex-col gap-1">
      {links.map((link) => {
        // "Ask" also owns /c/[id], so a thread keeps the right nav item lit.
        const active = link.exact
          ? pathname === link.href || pathname.startsWith("/c/")
          : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            onClick={() => setOpen(false)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-surface-strong text-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <link.icon className="size-4" strokeWidth={1.75} aria-hidden />
            {link.label}
            {link.label === "Library" && processing > 0 ? (
              <Pill tone="primary" className="ml-auto">
                {processing} working
              </Pill>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[248px_1fr]">
      <div className="flex h-14 items-center justify-between border-b border-border px-4 md:hidden">
        <Link href="/" aria-label="Saga">
          <Logo />
        </Link>
        <button
          type="button"
          className="inline-flex size-9 items-center justify-center rounded-md border border-border"
          aria-expanded={open}
          aria-label={open ? "Close navigation" : "Open navigation"}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X className="size-4" /> : <Menu className="size-4" />}
        </button>
      </div>
      {open ? <div className="border-b border-border p-4 md:hidden">{nav}</div> : null}

      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-border bg-canvas-soft p-4 md:flex">
        <Link href="/" className="px-2 py-2" aria-label="Saga">
          <Logo />
        </Link>
        <div className="mt-6 flex-1">{nav}</div>
        <div className="space-y-3 border-t border-border pt-4">
          <button
            type="button"
            onClick={toggle}
            className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {dark ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
            {dark ? "Light appearance" : "Dark appearance"}
          </button>
          {email ? (
            <div className="rounded-md border border-border bg-card p-3">
              <p className="truncate text-[13px] font-semibold" title={email}>
                {email}
              </p>
            </div>
          ) : null}
        </div>
      </aside>

      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function AppHeader({
  title,
  description,
  actions
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="border-b border-border px-5 py-6 md:px-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-display-md">{title}</h1>
          {description ? (
            <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
