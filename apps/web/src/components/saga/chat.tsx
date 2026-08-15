"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Copy,
  Info,
  MessageSquarePlus,
  MoreHorizontal,
  Paperclip,
  Pencil,
  RefreshCw,
  Search,
  Trash2
} from "lucide-react";
import { formatLocator, relative, time } from "@kb/shared";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  Input,
  Panel,
  Pill,
  Skeleton,
  SourceIcon,
  cn
} from "@kb/ui";
import type { Citation, Conversation, ConversationSummary, Message } from "@/types/api";
import { useConversations } from "@/lib/conversations-context";
import { useSources } from "@/lib/sources-context";
import { useToast } from "@/lib/toast";

/* ----------------------------- Conversation list ---------------------------- */

export function ConversationList({ activeId }: { activeId?: string }) {
  const { conversations, loading, rename, remove } = useConversations();
  const [query, setQuery] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [pendingDelete, setPendingDelete] = useState<ConversationSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const toast = useToast();

  const needle = query.trim().toLowerCase();
  const filtered = conversations.filter(
    (conversation) =>
      conversation.title.toLowerCase().includes(needle) ||
      conversation.preview.toLowerCase().includes(needle)
  );

  async function commitRename(conversation: ConversationSummary) {
    const title = draft.trim();
    setRenaming(null);
    if (!title || title === conversation.title) return;
    try {
      await rename(conversation.id, title);
    } catch {
      toast.error("Couldn't rename that conversation.");
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await remove(pendingDelete.id);
      setPendingDelete(null);
    } catch {
      toast.error("Couldn't delete that conversation.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col border-border lg:border-r">
      <div className="space-y-3 border-b border-border p-4">
        <Link
          href="/"
          className="flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary-active"
        >
          <MessageSquarePlus className="size-4" aria-hidden /> New conversation
        </Link>
        <div className="relative">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-soft"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search conversations"
            aria-label="Search conversations"
            className="h-10 pl-9 text-sm"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="space-y-2 p-2" aria-label="Loading conversations">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : filtered.length === 0 ? (
          <p className="px-3 py-8 text-center text-[13px] text-muted-foreground">
            {conversations.length === 0
              ? "No conversations yet. Ask your first question."
              : `Nothing matches “${query}”.`}
          </p>
        ) : (
          <ul className="space-y-1">
            {filtered.map((conversation) => (
              <li key={conversation.id} className="group relative">
                {renaming === conversation.id ? (
                  <form
                    className="p-1"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void commitRename(conversation);
                    }}
                  >
                    <Input
                      autoFocus
                      value={draft}
                      aria-label="Conversation title"
                      onChange={(event) => setDraft(event.target.value)}
                      onBlur={() => void commitRename(conversation)}
                      className="h-9 text-sm"
                    />
                  </form>
                ) : (
                  <Link
                    href={`/c/${conversation.id}`}
                    className={cn(
                      "block rounded-md px-3 py-2.5 pr-16 transition-colors",
                      activeId === conversation.id ? "bg-surface-strong" : "hover:bg-muted"
                    )}
                  >
                    <span className="line-clamp-2 text-[13px] font-semibold">
                      {conversation.title}
                    </span>
                    <span className="mt-1 line-clamp-1 block text-[12px] text-muted-foreground">
                      {conversation.preview}
                    </span>
                    <span className="mt-1 block text-[11px] text-muted-soft">
                      {conversation.updated_at ? relative(conversation.updated_at) : ""} ·{" "}
                      {conversation.message_count}{" "}
                      {conversation.message_count === 1 ? "message" : "messages"}
                    </span>
                  </Link>
                )}
                <div className="absolute top-2 right-2 hidden gap-1 group-hover:flex group-focus-within:flex">
                  <IconButton
                    label={`Rename ${conversation.title}`}
                    onClick={() => {
                      setRenaming(conversation.id);
                      setDraft(conversation.title);
                    }}
                  >
                    <Pencil className="size-3.5" />
                  </IconButton>
                  <IconButton
                    label={`Delete ${conversation.title}`}
                    onClick={() => setPendingDelete(conversation)}
                  >
                    <Trash2 className="size-3.5" />
                  </IconButton>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {pendingDelete ? (
        <ConfirmDialog
          title="Delete this conversation?"
          body={`“${pendingDelete.title}” and every message in it will be removed. This can't be undone.`}
          confirmLabel="Delete conversation"
          busy={deleting}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setPendingDelete(null)}
        />
      ) : null}
    </div>
  );
}

function IconButton({
  label,
  onClick,
  children
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="inline-flex size-7 items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:text-foreground"
    >
      {children}
    </button>
  );
}

/* --------------------------------- Composer -------------------------------- */

export function Composer({
  onSend,
  disabled,
  hint
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  hint?: string;
}) {
  const [value, setValue] = useState("");
  const { counts } = useSources();
  const { ready, processing } = counts;

  return (
    <div className="border-t border-border bg-background p-4 md:px-8 md:py-5">
      <form
        className="mx-auto flex max-w-3xl items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!value.trim() || disabled) return;
          onSend(value.trim());
          setValue("");
        }}
      >
        <label htmlFor="composer" className="sr-only">
          Ask a question of your library
        </label>
        <textarea
          id="composer"
          rows={1}
          value={value}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={ready === 0 ? "Add a source before asking" : "Ask anything in your library…"}
          className="max-h-40 min-h-11 flex-1 resize-y rounded-md border border-border bg-card px-4 py-3 text-[15px] placeholder:text-muted-soft"
        />
        <Button type="submit" disabled={disabled || !value.trim()} className="h-11 px-4">
          <span className="sr-only sm:not-sr-only">Ask</span>
        </Button>
      </form>
      <p className="mx-auto mt-2 max-w-3xl text-[12px] text-muted-foreground">
        {hint ??
          `Answering from ${ready} ready ${ready === 1 ? "source" : "sources"}${
            processing ? ` · ${processing} still being prepared` : ""
          }. Enter to send, Shift+Enter for a new line.`}
      </p>
    </div>
  );
}

/* ---------------------------------- Thread --------------------------------- */

export function Thread({
  conversation,
  streamingId,
  onDeleteMessage
}: {
  conversation: Conversation;
  streamingId?: string | null;
  onDeleteMessage?: (messageId: string) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [conversation.messages.length, streamingId]);

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 px-5 py-8 md:px-8">
      {conversation.messages.map((message) => (
        <MessageBlock
          key={message.id}
          message={message}
          streaming={streamingId === message.id}
          onDelete={onDeleteMessage}
          conversationId={conversation.id || undefined}
        />
      ))}
      <div ref={endRef} />
    </div>
  );
}

export function MessageBlock({
  message,
  streaming,
  onDelete,
  conversationId
}: {
  message: Message;
  streaming?: boolean;
  onDelete?: (messageId: string) => void;
  conversationId?: string;
}) {
  const [copied, setCopied] = useState(false);

  if (message.role === "user") {
    return (
      <article aria-label="Your question" className="flex justify-end">
        <p className="max-w-[85%] rounded-lg rounded-br-xs bg-surface-strong px-4 py-3 text-[15px] font-medium">
          {message.content}
        </p>
      </article>
    );
  }

  return (
    <article aria-label="Saga's answer" className="space-y-4">
      {message.insufficient_context ? (
        <div className="rounded-lg border border-dashed border-border-strong bg-canvas-soft p-5">
          <Pill>
            <Info className="size-3" aria-hidden /> Not enough in your sources
          </Pill>
          <p className="mt-3 text-[15px] leading-relaxed">{message.content}</p>
          <p className="mt-3 text-[13px] text-muted-foreground">
            This isn&apos;t an error — Saga found nothing close enough to quote. Add a source that
            covers it, or rephrase the question.
          </p>
        </div>
      ) : (
        <div
          className="space-y-3 text-[15px] leading-relaxed"
          aria-live={streaming ? "polite" : undefined}
        >
          {message.content === "" && streaming ? (
            <div className="space-y-2">
              <Skeleton className="w-3/4" />
              <Skeleton className="w-full" />
              <Skeleton className="w-2/3" />
            </div>
          ) : (
            message.content.split("\n\n").map((paragraph, index, all) => (
              <p key={index}>
                {paragraph}
                {streaming && index === all.length - 1 ? (
                  <span className="stream-caret text-primary">▌</span>
                ) : null}
              </p>
            ))
          )}
        </div>
      )}

      {!streaming && message.citations.length > 0 ? (
        <SourcesChip
          citations={message.citations}
          messageId={message.id}
          conversationId={conversationId}
        />
      ) : null}

      {!streaming ? (
        <div className="flex items-center gap-1 text-muted-foreground">
          <SmallAction
            label={copied ? "Copied" : "Copy answer"}
            icon={Copy}
            onClick={() => {
              void navigator.clipboard?.writeText(message.content);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            }}
          />
          {onDelete ? (
            <SmallAction
              label="Delete message"
              icon={Trash2}
              onClick={() => onDelete(message.id)}
            />
          ) : null}
          {message.created_at ? (
            <span className="ml-auto text-[11px] text-muted-soft">{time(message.created_at)}</span>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function SmallAction({
  label,
  icon: Icon,
  onClick
}: {
  label: string;
  icon: typeof Copy;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] hover:bg-muted hover:text-foreground"
    >
      <Icon className="size-3.5" aria-hidden />
      {label}
    </button>
  );
}

/**
 * The answer's sources, collapsed to a single chip.
 *
 * Citations used to render as a stack of cards, each repeating the excerpt already quoted in
 * the answer above — so a three-source answer pushed the next question off the screen. The
 * chip states the count and gets out of the way; the detail is one click away for a reader
 * who wants to verify, which is the only time it matters.
 *
 * Rows are grouped by `asset_id`, because three hits in one PDF are one document to a reader,
 * not three sources.
 */
export function SourcesChip({
  citations,
  messageId,
  conversationId
}: {
  citations: Citation[];
  messageId: string;
  conversationId?: string;
}) {
  const [open, setOpen] = useState(false);
  const chipRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const { sources } = useSources();

  // Group by document, preserving the retrieval order the API returned. Each citation keeps
  // its ORIGINAL index — the viewer's `i` param refers to position in the full citation list,
  // so grouping must not renumber it.
  const documents: { assetId: string; citations: { citation: Citation; index: number }[] }[] = [];
  citations.forEach((citation, index) => {
    const existing = documents.find((entry) => entry.assetId === citation.asset_id);
    if (existing) existing.citations.push({ citation, index });
    else documents.push({ assetId: citation.asset_id, citations: [{ citation, index }] });
  });

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      chipRef.current?.focus(); // focus returns to the trigger, never to the page top
    }
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (popoverRef.current?.contains(target) || chipRef.current?.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  const label = `${citations.length} ${citations.length === 1 ? "source" : "sources"}`;

  return (
    <div className="relative">
      <button
        ref={chipRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={`${label} for this answer`}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1",
          "text-[12px] text-muted-foreground transition-colors",
          "hover:border-border-strong hover:text-foreground"
        )}
      >
        <Paperclip className="size-3.5" aria-hidden />
        {label}
        <ChevronDown
          className={cn("size-3.5 transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>

      {open ? (
        <div
          ref={popoverRef}
          role="group"
          aria-label={`${label} for this answer`}
          className={cn(
            "absolute left-0 z-20 mt-1.5 w-[min(28rem,calc(100vw-2rem))]",
            "hairline-panel overflow-hidden p-1 shadow-lg",
            "motion-safe:animate-in motion-safe:fade-in"
          )}
        >
          {documents.map((entry) => {
            const first = entry.citations[0]!;
            const source = sources.find((item) => item.id === entry.assetId);
            const title = source?.title ?? first.citation.filename;
            return (
              <div key={entry.assetId} className="p-1">
                <div className="flex items-center gap-2 px-1.5 pb-1">
                  <SourceIcon type={first.citation.source_type} className="size-5" />
                  <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{title}</span>
                </div>
                {entry.citations.map(({ citation, index }) => {
                  // `conv` lets the viewer fetch exactly one thread instead of scanning them
                  // all for the message the reader came from.
                  const query = new URLSearchParams({
                    cite: String(citation.chunk_index),
                    from: messageId,
                    i: String(index)
                  });
                  if (conversationId) query.set("conv", conversationId);
                  return (
                    <Link
                      key={`${citation.asset_id}-${citation.chunk_index}`}
                      href={`/view/${citation.asset_id}?${query.toString()}`}
                      onClick={() => setOpen(false)}
                      className={cn(
                        "flex items-center gap-2 rounded-md px-1.5 py-1.5",
                        "hover:bg-muted focus-visible:bg-muted"
                      )}
                    >
                      <Pill>{formatLocator(citation.locator)}</Pill>
                      <span
                        className={cn(
                          "ml-auto shrink-0 text-[12px]",
                          citation.score >= 0.8
                            ? "text-success"
                            : citation.score >= 0.6
                              ? "text-muted-foreground"
                              : "text-muted-soft"
                        )}
                      >
                        {Math.round(citation.score * 100)}%
                      </span>
                      <ChevronRight className="size-3.5 shrink-0 text-muted-soft" aria-hidden />
                    </Link>
                  );
                })}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------- Error states ------------------------------ */

export function ChatError({ message, onRetry }: { message?: string; onRetry: () => void }) {
  return (
    <Panel className="mx-auto max-w-3xl border-destructive/40 p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 text-destructive" aria-hidden />
        <div>
          <h3 className="text-[16px] font-semibold">That question didn&apos;t get through</h3>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {message ??
              "The connection dropped while Saga was answering. Nothing was saved, so you can ask it again as-is."}
          </p>
          <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
            <RefreshCw className="size-3.5" aria-hidden /> Try again
          </Button>
        </div>
      </div>
    </Panel>
  );
}

const SUGGESTIONS = [
  "What are the main conclusions across my sources?",
  "Summarise what I've added most recently.",
  "What do my sources disagree about?"
];

export function NewConversationEmpty({ onPick }: { onPick: (question: string) => void }) {
  const { counts } = useSources();

  if (counts.ready === 0) {
    return (
      <EmptyState
        icon={MoreHorizontal}
        title="Nothing to ask yet"
        body="Your library is empty, so there's nothing for Saga to answer from. Add a PDF, a deck, some notes, a recording or a YouTube link to begin."
        action={
          <Link
            href="/library"
            className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary-active"
          >
            Add your first source
          </Link>
        }
      />
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-5 py-16 text-center md:py-24">
      <h2 className="text-display-lg">Ask your library.</h2>
      <p className="mx-auto mt-3 max-w-lg text-[15px] text-muted-foreground">
        {counts.ready} {counts.ready === 1 ? "source is" : "sources are"} ready. Every answer comes
        back with the passages behind it, and you can open any of them at the exact page or
        timestamp.
      </p>
      <ul className="mt-8 space-y-2 text-left">
        {SUGGESTIONS.map((suggestion) => (
          <li key={suggestion}>
            <button
              type="button"
              onClick={() => onPick(suggestion)}
              className="w-full rounded-md border border-border bg-card px-4 py-3 text-left text-[14px] transition-colors hover:border-border-strong"
            >
              {suggestion}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
