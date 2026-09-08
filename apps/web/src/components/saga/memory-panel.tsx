"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Brain, Check, Pencil, Trash2, X } from "lucide-react";
import { relative } from "@kb/shared";
import { Button, ConfirmDialog, EmptyState, Panel, Pill, Skeleton, Textarea } from "@kb/ui";
import type { WorkspaceMemory } from "@/types/api";
import { useMemoriesStore } from "@/stores/memories-store";
import { toast } from "@/stores/toast-store";

/**
 * What the workspace remembers, and the controls that make remembering acceptable.
 *
 * A system that quietly accumulates facts about you and folds them into every future answer
 * is something that happens to you, not a feature. This is the entire difference: see what
 * was learned, correct it when it is wrong, delete it when it should never have been kept.
 * Nothing here is an advanced setting.
 *
 * One component, two frames. `/memory` renders it as a page and the header's Memory pill
 * opens the same URL as a drawer over whatever you were reading — so the thing you wanted to
 * check a remembered fact *against* is still on screen while you check it.
 */
export function MemoryPanel({ compact = false }: { compact?: boolean }) {
  const memories = useMemoriesStore((state) => state.memories);
  const enabled = useMemoriesStore((state) => state.enabled);
  const loading = useMemoriesStore((state) => state.loading);
  const ensureLoaded = useMemoriesStore((state) => state.ensureLoaded);
  const add = useMemoriesStore((state) => state.add);
  const edit = useMemoriesStore((state) => state.edit);
  const remove = useMemoriesStore((state) => state.remove);
  const forgetAll = useMemoriesStore((state) => state.forgetAll);

  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const [confirmingForgetAll, setConfirmingForgetAll] = useState(false);
  const [forgetting, setForgetting] = useState(false);

  useEffect(() => {
    void ensureLoaded();
  }, [ensureLoaded]);

  async function onAdd() {
    const content = draft.trim();
    if (!content) return;
    setAdding(true);
    try {
      await add(content);
      setDraft("");
    } catch {
      toast.error("Couldn't save that. Try again?");
    } finally {
      setAdding(false);
    }
  }

  return (
    <>
      {enabled === false ? (
        // The state this feature was silently in for its whole life: everything below worked,
        // and nothing stored here ever reached an answer. Saying so is the fix.
        <Panel className="mb-5 border-dashed p-4">
          <p className="text-[13px] font-medium">Memory is turned off for this workspace.</p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            Anything saved here would be kept but never used in an answer, so adding to it is
            disabled. Set <code>MEMORY_ENABLED=1</code> to turn it back on.
          </p>
        </Panel>
      ) : null}

      <Panel className="p-4">
        <label htmlFor="new-memory" className="text-[13px] font-medium">
          Tell Saga something to remember
        </label>
        <Textarea
          id="new-memory"
          rows={2}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="We refer to our customers as members, never users."
          className="mt-2 text-sm"
          disabled={enabled === false}
        />
        <div className="mt-2 flex justify-end">
          <Button
            size="sm"
            onClick={() => void onAdd()}
            disabled={!draft.trim() || adding || enabled === false}
          >
            {adding ? "Saving…" : "Remember this"}
          </Button>
        </div>
      </Panel>

      <div className="mt-5 space-y-3">
        {loading ? (
          <>
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </>
        ) : memories.length === 0 ? (
          <EmptyState
            icon={Brain}
            title="Nothing remembered yet"
            body="As you ask questions, Saga picks up durable facts about how you work and keeps them here. You can add one yourself above."
          />
        ) : (
          memories.map((memory) => (
            <MemoryRow
              key={memory.id}
              memory={memory}
              compact={compact}
              onSave={(content) => edit(memory.id, content)}
              onDelete={() => remove(memory.id)}
            />
          ))
        )}
      </div>

      {memories.length > 0 ? (
        <div className="mt-5 flex justify-end">
          <Button variant="ghost" size="sm" onClick={() => setConfirmingForgetAll(true)}>
            <Trash2 className="size-3.5" aria-hidden /> Forget everything
          </Button>
        </div>
      ) : null}

      {confirmingForgetAll ? (
        <ConfirmDialog
          title="Forget everything?"
          body={`This permanently deletes all ${memories.length} remembered facts. Saga will start again from nothing. Your sources and conversations are not affected.`}
          confirmLabel="Forget everything"
          confirmVariant="danger"
          busy={forgetting}
          onConfirm={async () => {
            setForgetting(true);
            try {
              await forgetAll();
              setConfirmingForgetAll(false);
            } catch {
              toast.error("Couldn't clear memory. Try again?");
            } finally {
              setForgetting(false);
            }
          }}
          onCancel={() => setConfirmingForgetAll(false)}
        />
      ) : null}
    </>
  );
}

function MemoryRow({
  memory,
  compact,
  onSave,
  onDelete
}: {
  memory: WorkspaceMemory;
  compact: boolean;
  onSave: (content: string) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(memory.content);
  const [busy, setBusy] = useState(false);

  async function save() {
    const content = draft.trim();
    if (!content || content === memory.content) {
      setEditing(false);
      return;
    }
    setBusy(true);
    try {
      await onSave(content);
      setEditing(false);
    } catch {
      toast.error("Couldn't update that. Try again?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel className="border-border-soft p-4">
      {editing ? (
        <>
          <Textarea
            rows={2}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label="Edit memory"
            className="text-sm"
          />
          <div className="mt-2 flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setDraft(memory.content);
                setEditing(false);
              }}
            >
              <X className="size-3.5" aria-hidden /> Cancel
            </Button>
            <Button size="sm" onClick={() => void save()} disabled={busy}>
              <Check className="size-3.5" aria-hidden /> {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </>
      ) : (
        // In the drawer the actions stack under the text rather than beside it: 420px is not
        // wide enough for both, and a truncated fact is the one thing this panel exists to
        // show in full.
        <div className={compact ? "" : "flex flex-wrap items-start gap-4"}>
          <div className="min-w-0 flex-1">
            <p className="text-[14px]">{memory.content}</p>
            <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
              {memory.kind === "preference" ? <Pill>Preference</Pill> : null}
              {memory.created_at ? <span>learned {relative(memory.created_at)}</span> : null}
              {memory.last_used_at ? <span>· used {relative(memory.last_used_at)}</span> : null}
              {memory.source_conversation_id ? (
                <Link
                  href={`/c/${memory.source_conversation_id}`}
                  className="underline hover:text-foreground"
                >
                  · from this conversation
                </Link>
              ) : null}
            </p>
          </div>
          <div className={compact ? "mt-2 flex gap-1" : "flex gap-1"}>
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
              <Pencil className="size-3.5" aria-hidden /> Edit
            </Button>
            <Button size="sm" variant="ghost" onClick={() => void onDelete()}>
              <Trash2 className="size-3.5" aria-hidden /> Forget
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}
