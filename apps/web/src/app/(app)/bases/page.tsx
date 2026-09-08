"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Database, GripVertical, MessageSquare, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Button, ConfirmDialog, EmptyState, Skeleton, cn } from "@kb/ui";
import type { KnowledgeBase } from "@/types/api";
import { baseInitial, baseTileClass } from "@/lib/base-colour";
import { setBaseDragData } from "@/lib/base-drag";
import { BaseEditor, useDeleteBase } from "@/components/saga/base-editor";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { useSourcesStore } from "@/stores/sources-store";

/**
 * Every knowledge base, as cards.
 *
 * A card is draggable onto the Chat tab, and also carries a plain Chat button that does the
 * same thing — the drag is the nicer gesture, the button is the one that works with a
 * keyboard, on a phone, and for anyone who never discovers the drag.
 */
export default function BasesPage() {
  const router = useRouter();
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const loading = useKnowledgeBasesStore((state) => state.loading);
  const ensureLoaded = useKnowledgeBasesStore((state) => state.ensureLoaded);
  const attachedIds = useKnowledgeBasesStore((state) => state.attachedIds);
  const setAttached = useKnowledgeBasesStore((state) => state.setAttached);
  const setDragging = useKnowledgeBasesStore((state) => state.setDragging);
  const draggingId = useKnowledgeBasesStore((state) => state.draggingId);
  const sources = useSourcesStore((state) => state.sources);
  const ensureSources = useSourcesStore((state) => state.ensureLoaded);
  const deleteBase = useDeleteBase();

  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<KnowledgeBase | null>(null);
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<KnowledgeBase | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    void ensureLoaded();
    void ensureSources();
  }, [ensureLoaded, ensureSources]);

  // Counted from the library the client already holds, not from `source_count` on the base:
  // that figure is a snapshot from the last list call, and filing a source into a base here
  // should move the number on this page immediately.
  const counts = useMemo(() => {
    const tally = new Map<string, number>();
    for (const source of sources) {
      for (const id of source.base_ids) tally.set(id, (tally.get(id) ?? 0) + 1);
    }
    return tally;
  }, [sources]);

  const needle = filter.trim().toLowerCase();
  const shown = needle
    ? bases.filter(
        (base) =>
          base.name.toLowerCase().includes(needle) ||
          (base.description ?? "").toLowerCase().includes(needle)
      )
    : bases;

  function openInChat(base: KnowledgeBase) {
    if (!attachedIds.includes(base.id)) setAttached([...attachedIds, base.id]);
    router.push("/");
  }

  return (
    <div className="h-full overflow-y-auto">
      {draggingId ? (
        <div className="sticky top-0 z-30 flex items-center gap-2.5 border-b border-primary-soft-border bg-primary-soft px-6 py-2 text-xs font-semibold text-primary">
          <span className="size-2 animate-ping rounded-full bg-primary" />
          Drop it on the <strong>Chat</strong> tab above to ask questions of it.
        </div>
      ) : null}

      <div className="border-b border-border-soft bg-card px-6 py-6 md:px-8">
        <div className="mx-auto flex max-w-6xl flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-display-sm font-semibold tracking-tight">Knowledge bases</h1>
            <p className="mt-0.5 max-w-2xl text-xs text-muted-foreground">
              Separate libraries of sources. A question is only answered from the bases you
              attach, so nothing from one project leaks into another.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative w-full sm:w-60">
              <Search
                className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground"
                aria-hidden
              />
              <input
                type="search"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Filter bases…"
                aria-label="Filter knowledge bases"
                className="w-full rounded-xl border border-transparent bg-muted py-2 pl-9 pr-3 text-xs placeholder:text-muted-foreground focus:border-primary focus:bg-card focus:outline-none"
              />
            </div>
            <Button size="sm" className="shrink-0" onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden /> New base
            </Button>
          </div>
        </div>
      </div>

      <div className="mx-auto w-full max-w-6xl p-6 md:p-8">
        {loading && bases.length === 0 ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((key) => (
              <Skeleton key={key} className="h-44 rounded-2xl" />
            ))}
          </div>
        ) : shown.length === 0 ? (
          <EmptyState
            icon={Database}
            title={needle ? "No bases match that" : "No knowledge bases yet"}
            body={
              needle
                ? "Try a shorter search."
                : "Create one, then upload the sources it should answer from."
            }
            {...(needle
              ? {}
              : {
                  action: (
                    <Button size="sm" onClick={() => setCreating(true)}>
                      <Plus className="size-4" aria-hidden /> New base
                    </Button>
                  )
                })}
          />
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((base) => {
              const count = counts.get(base.id) ?? base.source_count;
              const dragged = draggingId === base.id;
              const attached = attachedIds.includes(base.id);
              return (
                <div
                  key={base.id}
                  draggable
                  onDragStart={(event) => {
                    setBaseDragData(event, base.id);
                    setDragging(base.id);
                  }}
                  onDragEnd={() => setDragging(null)}
                  className={cn(
                    "group flex cursor-grab select-none flex-col justify-between rounded-2xl border bg-card p-5 shadow-xs transition-all active:cursor-grabbing",
                    dragged
                      ? "border-2 border-dashed border-primary bg-primary-soft/40 opacity-60"
                      : "border-border-soft hover:border-primary hover:shadow-md"
                  )}
                >
                  <div>
                    <div className="mb-3 flex items-start justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-3">
                        <span
                          aria-hidden
                          className={cn(
                            "flex size-9 shrink-0 items-center justify-center rounded-xl text-sm font-bold text-white shadow-xs",
                            baseTileClass(base)
                          )}
                        >
                          {baseInitial(base.name)}
                        </span>
                        <div className="min-w-0">
                          <h2 className="truncate text-sm font-semibold transition-colors group-hover:text-primary">
                            {base.name}
                          </h2>
                          <span className="text-[11px] text-muted-foreground">
                            {count} {count === 1 ? "source" : "sources"}
                            {attached ? " · attached to chat" : ""}
                          </span>
                        </div>
                      </div>

                      <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                        <IconAction label={`Edit ${base.name}`} onClick={() => setEditing(base)}>
                          <Pencil className="size-3.5" aria-hidden />
                        </IconAction>
                        <IconAction
                          label={`Delete ${base.name}`}
                          danger
                          onClick={() => setPendingDelete(base)}
                        >
                          <Trash2 className="size-3.5" aria-hidden />
                        </IconAction>
                      </div>
                    </div>

                    <p className="mb-4 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                      {base.description || "No description."}
                    </p>
                  </div>

                  <div className="flex items-center justify-between gap-2 border-t border-border-soft pt-4">
                    <span
                      aria-hidden
                      title="Drag this card onto the Chat tab"
                      className="flex items-center gap-1.5 rounded-lg border border-border bg-muted px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors group-hover:border-primary/50 group-hover:text-primary"
                    >
                      <GripVertical className="size-3.5" aria-hidden />
                      Drag to Chat
                    </span>
                    <div className="flex items-center gap-1.5">
                      <Link
                        href={`/bases/${base.id}`}
                        className="rounded-lg px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      >
                        Manage
                      </Link>
                      <Button
                        variant="secondary"
                        size="sm"
                        className="border-border"
                        onClick={() => openInChat(base)}
                      >
                        <MessageSquare className="size-3.5" aria-hidden /> Chat
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {creating ? <BaseEditor base={null} onClose={() => setCreating(false)} /> : null}
      {editing ? <BaseEditor base={editing} onClose={() => setEditing(null)} /> : null}
      {pendingDelete ? (
        <ConfirmDialog
          title={`Delete “${pendingDelete.name}”?`}
          body={`This removes the base, its ${
            counts.get(pendingDelete.id) ?? pendingDelete.source_count
          } source(s), and every conversation and remembered fact belonging to it. It cannot be undone.`}
          confirmLabel="Delete base"
          busy={deleting}
          onCancel={() => setPendingDelete(null)}
          onConfirm={async () => {
            setDeleting(true);
            const ok = await deleteBase(pendingDelete);
            setDeleting(false);
            setPendingDelete(null);
            // The library still holds sources that belonged to it, and their memberships are
            // gone server-side; re-reading is cheaper than reconciling that here.
            if (ok) void useSourcesStore.getState().refresh();
          }}
        />
      ) : null}
    </div>
  );
}

function IconAction({
  label,
  onClick,
  danger = false,
  children
}: {
  label: string;
  onClick: () => void;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={cn(
        "rounded p-1 text-muted-foreground transition-colors",
        danger ? "hover:bg-destructive/10 hover:text-destructive" : "hover:bg-muted hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}
