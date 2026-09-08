"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Copy,
  Info,
  MessageSquarePlus,
  MoreHorizontal,
  Paperclip,
  Pencil,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  X
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
// Its own entry point: the markdown parser should load with the chat, not with the app.
import { Prose } from "@kb/ui/markdown";
import type {
  AnswerStatus,
  AnswerTrace,
  Citation,
  Conversation,
  ConversationSummary,
  GroundingReport,
  Message,
  Rating,
  TraceHop
} from "@/types/api";
import { clearFeedback, setFeedback } from "@/lib/api";
import { useConversationsStore } from "@/stores/conversations-store";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { useSourcesStore } from "@/stores/sources-store";
import { baseDotClass } from "@/lib/base-colour";
import { readBaseDragData } from "@/lib/base-drag";
import { toast } from "@/stores/toast-store";

/* ----------------------------- Conversation list ---------------------------- */

export function ConversationList({ activeId }: { activeId?: string }) {
  const conversations = useConversationsStore((state) => state.conversations);
  const loading = useConversationsStore((state) => state.loading);
  const rename = useConversationsStore((state) => state.rename);
  const remove = useConversationsStore((state) => state.remove);
  const [query, setQuery] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [pendingDelete, setPendingDelete] = useState<ConversationSummary | null>(null);
  const [deleting, setDeleting] = useState(false);

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
    <div className="flex h-full min-h-0 flex-col bg-card lg:border-r lg:border-border-soft">
      <div className="space-y-3 border-b border-border-soft p-3">
        <Link
          href="/"
          className="flex items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-xs transition-colors hover:bg-primary-active"
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
            className="h-9 rounded-xl border-transparent bg-muted pl-9 text-[13px] focus:border-primary focus:bg-card"
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
                      "block rounded-xl px-3 py-2.5 pr-16 transition-colors",
                      activeId === conversation.id
                        ? "border border-primary-soft-border bg-primary-soft"
                        : "border border-transparent hover:bg-muted"
                    )}
                  >
                    <span className="flex items-start gap-2">
                      <BaseDot baseId={conversation.knowledge_base_id} />
                      <span className="line-clamp-2 text-[13px] font-semibold">
                        {conversation.title}
                      </span>
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

/**
 * The colour of the base a thread was started in.
 *
 * Renders nothing when the base is gone or not loaded yet, rather than a grey placeholder:
 * an absent dot says less than a dot of the wrong colour would say wrongly.
 */
function BaseDot({ baseId }: { baseId: string }) {
  const base = useKnowledgeBasesStore((state) =>
    state.bases.find((item) => item.id === baseId)
  );
  if (!base) return null;
  return (
    <span
      title={base.name}
      aria-hidden
      className={cn("mt-1.5 size-2 shrink-0 rounded-full", baseDotClass(base))}
    />
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
  const ready = useSourcesStore((state) => state.counts.ready);
  const processing = useSourcesStore((state) => state.counts.processing);

  return (
    <div className="border-t border-border-soft bg-card px-4 pb-4 pt-3 md:px-8">
      <div className="mx-auto max-w-3xl">
        <AttachedBases />
        <form
          className="mt-2 flex items-end gap-2 rounded-2xl border border-border bg-background p-2 focus-within:border-primary"
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
            className="max-h-40 min-h-10 flex-1 resize-y bg-transparent px-2 py-2 text-[15px] placeholder:text-muted-soft focus:outline-none"
          />
          <Button
            type="submit"
            disabled={disabled || !value.trim()}
            className="size-10 shrink-0 rounded-xl px-0"
            aria-label="Ask"
          >
            <Send className="size-4" aria-hidden />
          </Button>
        </form>
        <p className="mt-2 text-[12px] text-muted-foreground">
          {hint ??
            `Answering from ${ready} ready ${ready === 1 ? "source" : "sources"}${
              processing ? ` · ${processing} still being prepared` : ""
            }. Enter to send, Shift+Enter for a new line.`}
        </p>
      </div>
    </div>
  );
}

/**
 * The bases this question will be answered from, and a drop target for adding one.
 *
 * The row is always visible, even with a single base attached. Which corpus an answer came
 * from is the one thing a reader cannot check afterwards by reading the answer, so it is
 * stated before the question is asked rather than explained after.
 */
function AttachedBases() {
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const attachedIds = useKnowledgeBasesStore((state) => state.attachedIds);
  const toggleAttached = useKnowledgeBasesStore((state) => state.toggleAttached);
  const setAttached = useKnowledgeBasesStore((state) => state.setAttached);
  const setDragging = useKnowledgeBasesStore((state) => state.setDragging);
  const dragging = useKnowledgeBasesStore((state) => state.draggingId);
  const [over, setOver] = useState(false);
  const [picking, setPicking] = useState(false);

  const attached = bases.filter((base) => attachedIds.includes(base.id));
  const rest = bases.filter((base) => !attachedIds.includes(base.id));

  if (bases.length === 0) return null;

  return (
    <div
      onDragOver={(event) => {
        if (!dragging) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const id = readBaseDragData(event) || dragging;
        setDragging(null);
        if (id && !attachedIds.includes(id)) setAttached([...attachedIds, id]);
      }}
      className={cn(
        "relative flex flex-wrap items-center gap-1.5 rounded-xl border border-dashed px-2 py-1.5 transition-colors",
        over ? "border-primary bg-primary-soft" : dragging ? "border-primary/50" : "border-transparent"
      )}
    >
      <span className="text-[11px] font-medium text-muted-foreground">Answering from</span>
      {attached.map((base) => (
        <span
          key={base.id}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted py-0.5 pl-2 pr-1 text-[11px] font-medium"
        >
          <span aria-hidden className={cn("size-2 rounded-full", baseDotClass(base))} />
          {base.name}
          {attached.length > 1 ? (
            <button
              type="button"
              onClick={() => toggleAttached(base.id)}
              title={`Stop answering from ${base.name}`}
              aria-label={`Stop answering from ${base.name}`}
              className="rounded-full p-0.5 text-muted-soft hover:bg-surface-strong hover:text-foreground"
            >
              <X className="size-3" aria-hidden />
            </button>
          ) : null}
        </span>
      ))}

      {rest.length > 0 ? (
        <button
          type="button"
          onClick={() => setPicking((value) => !value)}
          aria-expanded={picking}
          aria-haspopup="menu"
          className="inline-flex items-center gap-1 rounded-full border border-dashed border-border-strong px-2 py-0.5 text-[11px] font-medium text-muted-foreground hover:border-primary hover:text-primary"
        >
          <Paperclip className="size-3" aria-hidden /> Attach a base
        </button>
      ) : null}

      {picking ? (
        <>
          {/* Click-away, not a focus trap: the composer behind it stays readable. */}
          <button
            type="button"
            aria-label="Close"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setPicking(false)}
          />
          <Panel className="absolute bottom-full left-0 z-20 mb-1 w-64 p-1 shadow-lg">
            <ul role="menu" className="max-h-56 overflow-y-auto">
              {rest.map((base) => (
                <li key={base.id}>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      toggleAttached(base.id);
                      setPicking(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-muted"
                  >
                    <span aria-hidden className={cn("size-2 rounded-full", baseDotClass(base))} />
                    <span className="truncate">{base.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        </>
      ) : null}
    </div>
  );
}

/* ---------------------------------- Thread --------------------------------- */

export function Thread({
  conversation,
  streamingId,
  onDeleteMessage,
  onAsk
}: {
  conversation: Conversation;
  streamingId?: string | null;
  onDeleteMessage?: (messageId: string) => void;
  /** Asking a suggested follow-up. Absent means suggestions are not offered. */
  onAsk?: (question: string) => void;
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
          {...(onAsk ? { onAsk } : {})}
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
  conversationId,
  onAsk
}: {
  message: Message;
  streaming?: boolean;
  onDelete?: (messageId: string) => void;
  conversationId?: string;
  onAsk?: (question: string) => void;
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
            <div className="space-y-3">
              <AnswerProgress status={message.status} />
              <Skeleton className="w-3/4" />
              <Skeleton className="w-full" />
              <Skeleton className="w-2/3" />
            </div>
          ) : (
            <Prose streaming={streaming}>{message.content}</Prose>
          )}
        </div>
      )}

      {message.citations.length > 0 ? (
        <CitationSet
          citations={message.citations}
          messageId={message.id}
          conversationId={conversationId}
          grounding={message.grounding}
        />
      ) : null}

      {!streaming && onAsk && message.suggestions?.length ? (
        <FollowUps questions={message.suggestions} onAsk={onAsk} />
      ) : null}

      {!streaming ? (
        <AnswerTracePanel trace={message.trace} grounding={message.grounding} />
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
          {conversationId ? (
            <FeedbackControl
              conversationId={conversationId}
              messageId={message.id}
              value={message.feedback}
            />
          ) : null}
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

/**
 * Questions the passages behind this answer could also answer.
 *
 * Grounded, not generated from the topic: the server writes them while looking at what was
 * actually retrieved, so a suggestion that leads to "I could not find this" is not offered.
 * A suggestion the library cannot honour is worse than none, because the product proposed it.
 */
function FollowUps({
  questions,
  onAsk
}: {
  questions: string[];
  onAsk: (question: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <p className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
        <Sparkles className="size-3" aria-hidden /> You could also ask
      </p>
      <div className="flex flex-wrap gap-1.5">
        {questions.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onAsk(question)}
            className="rounded-full border border-border bg-card px-3 py-1.5 text-left text-[13px] text-muted-foreground transition-colors hover:border-primary hover:bg-primary-soft hover:text-primary"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}

function SmallAction({
  label,
  icon: Icon,
  onClick,
  active = false,
  hideLabel = false
}: {
  label: string;
  icon: typeof Copy;
  onClick: () => void;
  /** Renders the pressed state, and is announced — this is a toggle, not a link. */
  active?: boolean;
  /** Icon-only, with the label kept for screen readers. For actions that come in pairs. */
  hideLabel?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={hideLabel ? label : undefined}
      title={hideLabel ? label : undefined}
      // `cn` here is a naive join with no tailwind-merge, so the active colour has to come
      // last to win — there is no conflict resolution, only string order.
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] hover:bg-muted hover:text-foreground",
        active && "text-primary"
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {hideLabel ? null : label}
    </button>
  );
}

/**
 * Thumbs up/down on an answer.
 *
 * The only signal in the whole pipeline that does not come from a model grading its own
 * work — the reranker, the sufficiency grader and the grounding checker are all the same
 * family of model judging its own output. That makes each click worth more than anything
 * else recorded about an answer, which is why it is worth surfacing this plainly rather
 * than hiding it behind a menu.
 *
 * Clicking the active rating retracts it. State is optimistic and reverts on failure, the
 * same way `useAsk` patches messages: a thumb that visibly fails to register reads as a
 * broken button, and a thumb that lies is worse.
 */
function FeedbackControl({
  conversationId,
  messageId,
  value
}: {
  conversationId: string;
  messageId: string;
  value?: Rating | null;
}) {
  const [rating, setRating] = useState<Rating | null>(value ?? null);

  // A reload, or switching threads, replaces the message this control is mounted against.
  useEffect(() => setRating(value ?? null), [value, messageId]);

  async function vote(next: Rating) {
    const previous = rating;
    const retracting = previous === next;
    setRating(retracting ? null : next);
    try {
      if (retracting) await clearFeedback(conversationId, messageId);
      else await setFeedback(conversationId, messageId, next);
    } catch {
      setRating(previous);
    }
  }

  return (
    <>
      <SmallAction
        label="Good answer"
        icon={ThumbsUp}
        hideLabel
        active={rating === 1}
        onClick={() => void vote(1)}
      />
      <SmallAction
        label="Bad answer"
        icon={ThumbsDown}
        hideLabel
        active={rating === -1}
        onClick={() => void vote(-1)}
      />
    </>
  );
}

/**
 * What the pipeline is doing before the first token arrives.
 *
 * The answer takes a few seconds — retrieval, judging, possibly a second hop — and silence
 * is the failure mode users actually notice. Naming the stage turns a wait into progress.
 */
/**
 * What the agent is doing, right now.
 *
 * The loop reports every phase boundary rather than one flat "searching", because the
 * retrieval loop is the longest stretch of answering a question and a label that does not
 * change for five seconds reads as a hang. Hop numbers only appear on a second pass — saying
 * "hop 1 of 2" on the common single-hop path is noise, not information.
 */
function AnswerProgress({ status }: { status?: AnswerStatus | null }) {
  if (!status) return null;

  const rerun = (status.hop ?? 1) > 1;
  const label = describeStage(status, rerun);
  const hops = rerun ? ` (hop ${status.hop} of ${status.of})` : "";

  return (
    <p aria-live="polite" className="text-[13px] text-muted-foreground">
      {label}
      {hops}…
    </p>
  );
}

function describeStage(status: AnswerStatus, rerun: boolean): string {
  switch (status.stage) {
    case "resolving":
      return "Understanding the question";
    case "searching":
      return rerun ? "Searching again" : "Searching your sources";
    case "ranking":
      return status.candidates
        ? `Weighing ${status.candidates} passages`
        : "Weighing what came back";
    case "grading":
      return "Checking that's enough to answer";
    case "rewriting":
      return `Rephrasing the search${status.strategy ? ` — ${strategyLabel(status.strategy)}` : ""}`;
    case "generating":
      return "Writing the answer";
    case "reading":
      return status.sources
        ? `Reading ${status.sources} passage${status.sources === 1 ? "" : "s"}`
        : "Reading your sources";
  }
}

/** The loop's internal strategy names, in words a reader of the UI would use. */
function strategyLabel(strategy: string): string {
  switch (strategy) {
    case "initial":
      return "first attempt";
    case "broaden":
      return "broadened";
    case "decompose":
      return "split into parts";
    case "hyde":
      return "searching by example answer";
    default:
      return strategy;
  }
}


/**
 * How the answer was reached, collapsed by default.
 *
 * Persisted with the message rather than held in the tab that watched it stream, so it is
 * still here after a reload. Answers written before the trace existed simply have none, and
 * this renders nothing for them rather than an empty shell.
 */
function AnswerTracePanel({
  trace,
  grounding
}: {
  trace?: AnswerTrace | null;
  grounding?: GroundingReport | null;
}) {
  const [open, setOpen] = useState(false);
  if (!trace || trace.hops.length === 0) return null;

  const hops = trace.hops.length;
  const summary = `${hops} ${hops === 1 ? "search" : "searches"}${
    trace.degraded ? " · ranking unavailable" : ""
  }`;

  return (
    <div className="text-[13px]">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronRight
          className={cn("size-3 transition-transform", open && "rotate-90")}
          aria-hidden
        />
        How this answer was found
        <span className="text-muted-foreground/70">· {summary}</span>
      </button>

      {open ? (
        <ol className="mt-2 space-y-1.5 border-l border-border pl-3 text-muted-foreground">
          <TraceRow label="Understood" detail={trace.resolved_query} />
          {trace.memories_used ? (
            // The only place memory surfaces in an answer. It is never a citation — there is
            // no passage behind it to open — so it is disclosed here and nowhere else.
            <TraceRow
              label="Recalled"
              detail={`${trace.memories_used} ${
                trace.memories_used === 1 ? "thing" : "things"
              } from earlier conversations`}
            />
          ) : null}
          {trace.hops.map((hop) => (
            <TraceHopRows key={hop.hop} hop={hop} multiple={hops > 1} />
          ))}
          {grounding && grounding.checked > 0 ? (
            <TraceRow
              label="Verified"
              detail={`${grounding.supported} of ${grounding.checked} cited claims supported by their passage`}
            />
          ) : null}
        </ol>
      ) : null}
    </div>
  );
}

function TraceHopRows({ hop, multiple }: { hop: TraceHop; multiple: boolean }) {
  return (
    <>
      <TraceRow
        label={multiple ? `Search ${hop.hop}` : "Searched"}
        detail={`${strategyLabel(hop.strategy)} · ${hop.candidates} found, ${hop.kept} kept${
          hop.rerank_degraded ? " · ranked by score only" : ""
        }`}
      />
      <TraceRow
        label="Judged"
        detail={
          hop.sufficient
            ? "enough to answer"
            : hop.missing
              ? `not enough — missing ${hop.missing}`
              : "not enough"
        }
      />
    </>
  );
}

function TraceRow({ label, detail }: { label: string; detail: string }) {
  return (
    <li className="flex gap-2">
      <span className="shrink-0 font-medium text-foreground/70">{label}</span>
      <span className="min-w-0 break-words">{detail}</span>
    </li>
  );
}

/**
 * Whether each cited claim was actually supported by the passage it points at.
 *
 * Absent until the check reports back, which is after the answer has finished streaming —
 * so this appears rather than blocks. Nothing here is load-bearing: if the connection ended
 * before the report arrived, the answer stands on its citations as it always did.
 */
function VerifiedBadge({ grounding }: { grounding?: GroundingReport | null }) {
  if (!grounding) return null;

  const unsupported = grounding.unsupported.length + grounding.invalid.length;

  // An answer citing only invented ordinals has `checked === 0` — nothing could be checked,
  // because none of the numbers pointed at a real passage. That is the most alarming outcome
  // this checker can produce, and the old `checked === 0` guard silently swallowed it.
  if (grounding.invalid.length > 0) {
    return (
      <Pill>
        <AlertTriangle className="size-3" aria-hidden />
        {grounding.invalid.length} citation{grounding.invalid.length === 1 ? "" : "s"} point at
        no source
      </Pill>
    );
  }

  // Nothing checkable: the answer cited nothing, or the judge was unreachable. Say nothing
  // rather than imply a verdict in either direction.
  if (grounding.checked === 0) return null;

  if (grounding.verified) {
    return (
      <Pill>
        <Check className="size-3" aria-hidden /> Claims verified
      </Pill>
    );
  }

  return (
    <Pill>
      <Info className="size-3" aria-hidden />
      {unsupported} claim{unsupported === 1 ? "" : "s"} not supported by the cited passage
    </Pill>
  );
}

export function CitationSet({
  citations,
  messageId,
  conversationId,
  grounding
}: {
  citations: Citation[];
  messageId: string;
  conversationId?: string;
  grounding?: GroundingReport | null;
}) {
  return (
    <section aria-label="Sources for this answer" className="space-y-2">
      <div className="flex items-center gap-2">
        <h3 className="label-caps text-muted-foreground">
          {citations.length} cited {citations.length === 1 ? "passage" : "passages"}
        </h3>
        <VerifiedBadge grounding={grounding} />
      </div>
      {citations.map((citation, index) => (
        <CitationCard
          key={`${citation.asset_id}-${citation.chunk_index}`}
          citation={citation}
          index={index}
          messageId={messageId}
          conversationId={conversationId}
        />
      ))}
    </section>
  );
}

export function CitationCard({
  citation,
  index,
  messageId,
  conversationId
}: {
  citation: Citation;
  index: number;
  messageId: string;
  conversationId?: string;
}) {
  // Selecting the title string rather than the sources array matters here: there is one of
  // these per citation per message, and subscribing to the array would re-render every one
  // of them on every ingestion poll tick for an unrelated upload.
  const sourceTitle = useSourcesStore(
    (state) => state.sources.find((item) => item.id === citation.asset_id)?.title
  );
  // `conv` lets the viewer fetch exactly one thread instead of scanning them all for the
  // message the reader came from.
  const query = new URLSearchParams({
    cite: String(citation.chunk_index),
    from: messageId,
    i: String(index)
  });
  if (conversationId) query.set("conv", conversationId);
  return (
    <Link
      href={`/view/${citation.asset_id}?${query.toString()}`}
      className="flex items-start gap-3 rounded-md border border-border bg-card p-3 transition-colors hover:border-border-strong"
    >
      <SourceIcon type={citation.source_type} className="size-8" />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="max-w-full truncate text-[13px] font-semibold">
            {sourceTitle ?? citation.filename}
          </span>
          <Pill>{formatLocator(citation.locator)}</Pill>
          <span
            className={cn(
              "text-[12px]",
              citation.score >= 0.8
                ? "text-success"
                : citation.score >= 0.6
                  ? "text-muted-foreground"
                  : "text-muted-soft"
            )}
          >
            {Math.round(citation.score * 100)}% relevance
          </span>
        </span>
        <span className="mt-1.5 line-clamp-3 block font-serif text-[13px] italic leading-relaxed text-muted-foreground">
          “{citation.excerpt}”
        </span>
      </span>
      <ChevronRight className="mt-1 size-4 shrink-0 text-muted-soft" aria-hidden />
    </Link>
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
  const ready = useSourcesStore((state) => state.counts.ready);
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const attachedIds = useKnowledgeBasesStore((state) => state.attachedIds);
  const attached = bases.filter((base) => attachedIds.includes(base.id));

  if (ready === 0) {
    return (
      <div className="mx-auto max-w-2xl px-5 py-16 md:py-24">
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
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-5 py-16 text-center md:py-24">
      <span
        aria-hidden
        className="mx-auto flex size-12 items-center justify-center rounded-2xl border border-primary-soft-border bg-primary-soft text-primary"
      >
        <Sparkles className="size-6" />
      </span>
      <h2 className="mt-5 text-display-lg">Ask your library.</h2>
      <p className="mx-auto mt-3 max-w-lg text-[15px] text-muted-foreground">
        {ready} {ready === 1 ? "source is" : "sources are"} ready. Every answer comes back with
        the passages behind it, and you can open any of them at the exact page or timestamp.
      </p>

      {/* Which bases, spelled out. Two identical-looking questions can get different answers
          depending on what is attached, and this is the only moment before asking where that
          is worth saying. */}
      {attached.length > 0 ? (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-1.5">
          {attached.map((base) => (
            <span
              key={base.id}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium"
            >
              <span aria-hidden className={cn("size-2 rounded-full", baseDotClass(base))} />
              {base.name}
            </span>
          ))}
        </div>
      ) : null}

      <ul className="mt-8 space-y-2 text-left">
        {SUGGESTIONS.map((suggestion) => (
          <li key={suggestion}>
            <button
              type="button"
              onClick={() => onPick(suggestion)}
              className="w-full rounded-xl border border-border-soft bg-card px-4 py-3 text-left text-[14px] transition-colors hover:border-primary hover:bg-primary-soft/40"
            >
              {suggestion}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
