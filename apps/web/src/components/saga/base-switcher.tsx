"use client";

import { useEffect, useState } from "react";
import { Check, Library, Plus } from "lucide-react";
import { Button, Input, Panel, cn } from "@kb/ui";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { useConversationsStore } from "@/stores/conversations-store";
import { useSourcesStore } from "@/stores/sources-store";
import { toast } from "@/stores/toast-store";

/**
 * Which library you are in, and which libraries the chat reads from.
 *
 * Those are two different questions and the control shows both, because collapsing them
 * would make one of them impossible. Clicking a base *selects* it — the Library page and the
 * thread list follow, one place at a time, like a folder. The tick on the right *attaches*
 * it, and several can be attached at once, because answering across two libraries is the
 * thing this was built for.
 *
 * There is no dropdown primitive in the design system (no Radix, no shadcn), so this is a
 * button and a conditionally-rendered `Panel` — the same shape `ConfirmDialog` uses.
 */
export function BaseSwitcher({ onNavigate }: { onNavigate?: () => void }) {
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const selectedId = useKnowledgeBasesStore((state) => state.selectedId);
  const attachedIds = useKnowledgeBasesStore((state) => state.attachedIds);
  const loading = useKnowledgeBasesStore((state) => state.loading);
  const ensureLoaded = useKnowledgeBasesStore((state) => state.ensureLoaded);
  const select = useKnowledgeBasesStore((state) => state.select);
  const toggleAttached = useKnowledgeBasesStore((state) => state.toggleAttached);
  const add = useKnowledgeBasesStore((state) => state.add);

  const refreshConversations = useConversationsStore((state) => state.refresh);
  const refreshSources = useSourcesStore((state) => state.refresh);

  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ensureLoaded();
  }, [ensureLoaded]);

  const selected = bases.find((base) => base.id === selectedId) ?? null;

  function pick(id: string) {
    select(id);
    setOpen(false);
    onNavigate?.();
    // Both lists are scoped to the selected base, so they have to be re-fetched rather than
    // filtered client-side — the client only ever held one base's worth of rows.
    void refreshConversations();
    void refreshSources();
  }

  async function createBase() {
    const clean = name.trim();
    if (!clean) return;
    setBusy(true);
    try {
      await add(clean);
      setName("");
      setCreating(false);
      setOpen(false);
      void refreshConversations();
      void refreshSources();
    } catch {
      toast.error("Couldn't create that. Is the name already taken?");
    } finally {
      setBusy(false);
    }
  }

  if (loading && bases.length === 0) {
    return <div className="h-9 animate-pulse rounded-md bg-muted" />;
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex w-full items-center gap-2 rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-muted"
      >
        <Library className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-medium">
          {selected?.name ?? "Knowledge base"}
        </span>
        {attachedIds.length > 1 ? (
          <span className="shrink-0 text-[11px] text-muted-foreground">
            +{attachedIds.length - 1}
          </span>
        ) : null}
      </button>

      {open ? (
        <>
          {/* Click-away. A plain overlay rather than a focus trap: this is a menu, and the
              page behind it stays readable while it is open. */}
          <button
            type="button"
            aria-label="Close"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <Panel className="absolute left-0 right-0 top-full z-20 mt-1 p-1 shadow-lg">
            <p className="px-2 py-1.5 text-[11px] text-muted-foreground">
              Tick the bases to answer from
            </p>
            <ul role="menu" className="max-h-64 overflow-y-auto">
              {bases.map((base) => {
                const attached = attachedIds.includes(base.id);
                return (
                  <li key={base.id} className="flex items-center gap-1">
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => pick(base.id)}
                      className={cn(
                        "min-w-0 flex-1 rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-muted",
                        base.id === selectedId && "font-medium"
                      )}
                    >
                      <span className="block truncate">{base.name}</span>
                      <span className="block text-[11px] text-muted-foreground">
                        {base.source_count} {base.source_count === 1 ? "source" : "sources"}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleAttached(base.id)}
                      aria-pressed={attached}
                      aria-label={
                        attached ? `Stop answering from ${base.name}` : `Also answer from ${base.name}`
                      }
                      title={attached ? "Answering from this" : "Not answering from this"}
                      className={cn(
                        "mr-1 inline-flex size-7 shrink-0 items-center justify-center rounded-md border",
                        attached
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-border text-muted-soft hover:bg-muted"
                      )}
                    >
                      <Check className="size-3.5" aria-hidden />
                    </button>
                  </li>
                );
              })}
            </ul>

            <div className="mt-1 border-t border-border pt-1">
              {creating ? (
                <div className="flex gap-1 p-1">
                  <Input
                    autoFocus
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void createBase();
                      if (event.key === "Escape") setCreating(false);
                    }}
                    placeholder="Name"
                    aria-label="New knowledge base name"
                  />
                  <Button size="sm" onClick={() => void createBase()} disabled={busy || !name.trim()}>
                    Add
                  </Button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setCreating(true)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <Plus className="size-3.5" aria-hidden /> New knowledge base
                </button>
              )}
            </div>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
