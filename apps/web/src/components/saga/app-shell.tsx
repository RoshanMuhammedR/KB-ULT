"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Brain,
  Database,
  HelpCircle,
  Layers,
  MessageSquare,
  Moon,
  Sun,
  UserRound
} from "lucide-react";
import { Logo, cn, useTheme } from "@kb/ui";
import { useAuthStore } from "@/stores/auth-store";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { useMemoriesStore } from "@/stores/memories-store";
import { useSourcesStore } from "@/stores/sources-store";
import { BASE_DRAG_TYPE } from "@/lib/base-drag";
import { useOnboarding } from "@/components/saga/onboarding";

/**
 * The three places you can be, as tabs.
 *
 * They are real links, not local state: `/`, `/bases` and `/library` are addressable, and a
 * thread at `/c/{id}` keeps the Chat tab lit. That is the whole reason this is a `<nav>` of
 * `<Link>`s rather than the mock's `onSelectTab` — the look is the mock's, the URLs are the
 * product's.
 */
const TABS = [
  { href: "/", label: "Chat", short: "Chat", icon: MessageSquare, count: null },
  { href: "/bases", label: "Knowledge Bases", short: "Bases", icon: Database, count: "bases" },
  { href: "/library", label: "Document Library", short: "Library", icon: Layers, count: "sources" }
] as const;

function isActive(pathname: string, href: string): boolean {
  // Chat owns the thread routes too, so reading an old conversation does not un-light the tab
  // you are plainly still in.
  if (href === "/") return pathname === "/" || pathname.startsWith("/c/");
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <TopBar pathname={pathname} />
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}

function TopBar({ pathname }: { pathname: string }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const sourceCount = useSourcesStore((state) => state.counts.total);
  const memories = useMemoriesStore((state) => state.memories);
  const memoryEnabled = useMemoriesStore((state) => state.enabled);
  const ensureMemories = useMemoriesStore((state) => state.ensureLoaded);
  const email = useAuthStore((state) => state.session?.email ?? null);
  const { start: startTour } = useOnboarding();

  // The pill states a number, so the number has to be true before it is shown. Loading it
  // here rather than on /memory is the difference between "Memory (0)" meaning "nothing
  // learned" and it meaning "not asked yet".
  useEffect(() => {
    void ensureMemories();
  }, [ensureMemories]);

  const counts: Record<string, number> = { bases: bases.length, sources: sourceCount };

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-soft bg-card px-3 sm:px-5">
      <div className="flex min-w-0 items-center gap-3 sm:gap-6">
        <Link href="/" className="flex shrink-0 items-baseline gap-1.5" aria-label="Saga">
          <Logo />
          <span className="hidden rounded-full border border-primary-soft-border bg-primary-soft px-1.5 text-[10px] font-medium text-primary lg:inline">
            AI Studio
          </span>
        </Link>

        {/* Scrolls rather than wraps or overflows the header. Three tabs plus four controls
            do not fit a phone, and a horizontally scrolling *page* is the worst of the ways
            that can go. */}
        <nav
          aria-label="Sections"
          className="flex min-w-0 items-center gap-1 overflow-x-auto rounded-xl bg-muted p-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {TABS.map((tab) =>
            tab.href === "/" ? (
              <ChatTab key={tab.href} active={isActive(pathname, tab.href)} />
            ) : (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={isActive(pathname, tab.href) ? "page" : undefined}
                className={tabClass(isActive(pathname, tab.href))}
              >
                <tab.icon className="size-3.5 shrink-0" aria-hidden />
                <span className="hidden lg:inline">{tab.label}</span>
                <span className="lg:hidden">{tab.short}</span>
                {tab.count ? <TabCount value={counts[tab.count] ?? 0} /> : null}
              </Link>
            )
          )}
        </nav>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {/* Hidden on a phone, where the header has room for four controls and there are
            six. The tour is the one a returning user needs least. */}
        <IconButton label="Take the tour" onClick={startTour} className="hidden sm:inline-flex">
          <HelpCircle className="size-4" aria-hidden />
        </IconButton>

        <IconButton
          label={dark ? "Switch to light appearance" : "Switch to dark appearance"}
          onClick={toggle}
        >
          {dark ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
        </IconButton>

        <Link
          href="/memory"
          title={
            memoryEnabled === false
              ? "Memory is switched off for this workspace"
              : "What Saga remembers about this workspace"
          }
          className={cn(
            "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
            memoryEnabled === false
              ? "border-border bg-muted text-muted-foreground hover:bg-surface-strong"
              : "border-primary-soft-border bg-primary-soft text-primary hover:brightness-97"
          )}
        >
          <Brain className="size-3.5" aria-hidden />
          <span className="hidden sm:inline">Memory ({memories.length})</span>
          <span className="sm:hidden">{memories.length}</span>
        </Link>

        <Link
          href="/account"
          className="flex items-center gap-2 rounded-full border border-border py-1 pl-1 pr-2.5 transition-colors hover:bg-muted"
          title={email ?? "Account"}
        >
          <span className="flex size-6 items-center justify-center rounded-full bg-surface-strong text-muted-foreground">
            <UserRound className="size-3.5" aria-hidden />
          </span>
          <span className="hidden max-w-[140px] truncate text-xs font-medium sm:inline">
            {email ?? "Account"}
          </span>
        </Link>
      </div>
    </header>
  );
}

function tabClass(active: boolean) {
  return cn(
    "relative flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all sm:px-3.5",
    active
      ? "bg-card text-primary font-semibold shadow-xs"
      : "text-muted-foreground hover:bg-card/60 hover:text-foreground"
  );
}

function TabCount({ value }: { value: number }) {
  return (
    <span className="rounded-full bg-surface-strong px-1.5 text-[10px] text-muted-foreground">
      {value}
    </span>
  );
}

/**
 * The Chat tab, which is also a drop target for a knowledge base.
 *
 * Dropping a base here attaches it and opens the chat — the gesture asked for. It is an
 * enhancement, never the only route: every base card carries an explicit "Attach" button,
 * because a drag is unusable with a keyboard and unreliable on touch.
 */
function ChatTab({ active }: { active: boolean }) {
  const router = useRouter();
  const dragging = useKnowledgeBasesStore((state) => state.draggingId);
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const setDragging = useKnowledgeBasesStore((state) => state.setDragging);
  const attachedIds = useKnowledgeBasesStore((state) => state.attachedIds);
  const setAttached = useKnowledgeBasesStore((state) => state.setAttached);
  const [over, setOver] = useState(false);
  // Dragging onto a tab you are not on should take you there, the way a folder opens when
  // you hover it. The delay stops a drag that merely passes over the tab from hijacking the
  // page underneath.
  const hover = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => clearTimeout(hover.current ?? undefined), []);

  const draggedBase = bases.find((base) => base.id === dragging) ?? null;

  function attach(id: string) {
    if (!attachedIds.includes(id)) setAttached([...attachedIds, id]);
    router.push("/");
  }

  return (
    <Link
      href="/"
      aria-current={active ? "page" : undefined}
      title={draggedBase ? `Drop to chat with ${draggedBase.name}` : "Chat"}
      onDragOver={(event) => {
        if (!dragging) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        if (!over) setOver(true);
      }}
      onDragEnter={(event) => {
        if (!dragging) return;
        event.preventDefault();
        setOver(true);
        if (!active && !hover.current) {
          hover.current = setTimeout(() => router.push("/"), 400);
        }
      }}
      onDragLeave={() => {
        setOver(false);
        clearTimeout(hover.current ?? undefined);
        hover.current = null;
      }}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        clearTimeout(hover.current ?? undefined);
        hover.current = null;
        const id = event.dataTransfer.getData(BASE_DRAG_TYPE) || dragging;
        setDragging(null);
        if (id) attach(id);
      }}
      className={cn(
        tabClass(active),
        dragging && "border border-dashed border-primary/60 text-primary",
        over && "scale-105 border-primary bg-primary-soft text-primary shadow-md"
      )}
    >
      <MessageSquare className="size-3.5 shrink-0" aria-hidden />
      <span>Chat</span>
      {over ? <span className="text-[10px] font-bold">Drop</span> : null}
    </Link>
  );
}

function IconButton({
  label,
  onClick,
  className,
  children
}: {
  label: string;
  onClick: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={cn(
        "rounded-full border border-border p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        className
      )}
    >
      {children}
    </button>
  );
}

/**
 * A page heading inside a tab.
 *
 * Kept from the previous shell because several routes render it, but it is no longer the top
 * of the window — the tab bar is. So it is lighter than it was, and sits inside the scrolling
 * region rather than above it.
 */
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
    <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border-soft px-5 py-5 md:px-8">
      <div>
        <h1 className="text-display-sm font-semibold">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}
