"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Brain, Check, Pencil, Trash2, X } from "lucide-react";
import { relative } from "@kb/shared";
import { Button, ConfirmDialog, EmptyState, Panel, Pill, Skeleton, Textarea } from "@kb/ui";
import { AppHeader } from "@/components/saga/app-shell";
import type { WorkspaceMemory } from "@/types/api";
import { useMemoriesStore } from "@/stores/memories-store";
import { toast } from "@/stores/toast-store";

/**
 * What the workspace remembers, and the controls that make remembering acceptable.
 *
 * A system that quietly accumulates facts about you and folds them into every future answer
 * is something that happens to you, not a feature. This page is the entire difference: see
 * what was learned, correct it when it is wrong, delete it when it should never have been
 * kept. Nothing here is an advanced setting.
 */
export default function MemoryPage() {
  const memories = useMemoriesStore((state) => state.memories);
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
      <AppHeader
        title="Memory"
        description="Facts Saga has picked up about you and your work. It uses these as background in future answers — never as a source it cites."
        actions={
          memories.length > 0 ? (
            <Button variant="ghost" onClick={() => setConfirmingForgetAll(true)}>
              <Trash2 className="size-4" aria-hidden /> Forget everything
            </Button>
          ) : null
        }
      />

      <div className="px-5 py-6 md:px-8">
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
            className="mt-2"
          />
          <div className="mt-2 flex justify-end">
            <Button size="sm" onClick={() => void onAdd()} disabled={!draft.trim() || adding}>
              {adding ? "Saving..." : "Remember this"}
            </Button>
          </div>
        </Panel>

        <div className="mt-6 space-y-3">
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
                onSave={(content) => edit(memory.id, content)}
                onDelete={() => remove(memory.id)}
              />
            ))
          )}
        </div>
      </div>

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
  onSave,
  onDelete
}: {
  memory: WorkspaceMemory;
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
    <Panel className="p-4">
      {editing ? (
        <>
          <Textarea
            rows={2}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label="Edit memory"
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
              <Check className="size-3.5" aria-hidden /> {busy ? "Saving..." : "Save"}
            </Button>
          </div>
        </>
      ) : (
        <div className="flex flex-wrap items-start gap-4">
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
          <div className="flex gap-1">
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
