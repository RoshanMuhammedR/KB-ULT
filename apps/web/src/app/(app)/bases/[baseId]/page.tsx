"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  GripVertical,
  Link2,
  MessageSquare,
  Pencil,
  Plus,
  Search,
  X
} from "lucide-react";
import { sourceTitle, typeCopy } from "@kb/shared";
import {
  Button,
  EmptyState,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Skeleton,
  SourceIcon,
  StatusBadge,
  cn
} from "@kb/ui";
import type { KnowledgeAsset } from "@/types/api";
import { baseInitial, baseTileClass } from "@/lib/base-colour";
import { setBaseDragData } from "@/lib/base-drag";
import { BaseEditor } from "@/components/saga/base-editor";
import { AddSourceDialog } from "@/components/saga/add-source-dialog";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { useSourcesStore } from "@/stores/sources-store";
import { toast } from "@/stores/toast-store";
import * as api from "@/lib/api";

/**
 * One base: what is filed in it, and what could be.
 *
 * "Attach from library" is the screen that makes the many-to-many worth having — a contract
 * already ingested for Legal can be filed into Onboarding here without being uploaded,
 * parsed, chunked or embedded a second time.
 */
export default function BaseDetailPage() {
  const params = useParams<{ baseId: string }>();
  const baseId = params.baseId;
  const router = useRouter();

  const bases = useKnowledgeBasesStore((state) => state.bases);
  const basesLoading = useKnowledgeBasesStore((state) => state.loading);
  const ensureBases = useKnowledgeBasesStore((state) => state.ensureLoaded);
  const attachedIds = useKnowledgeBasesStore((state) => state.attachedIds);
  const setAttached = useKnowledgeBasesStore((state) => state.setAttached);
  const setDragging = useKnowledgeBasesStore((state) => state.setDragging);

  const sources = useSourcesStore((state) => state.sources);
  const sourcesLoading = useSourcesStore((state) => state.loading);
  const ensureSources = useSourcesStore((state) => state.ensureLoaded);
  const upsert = useSourcesStore((state) => state.upsert);

  const [editing, setEditing] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    void ensureBases();
    void ensureSources();
  }, [ensureBases, ensureSources]);

  const base = bases.find((item) => item.id === baseId) ?? null;

  const { inBase, available } = useMemo(() => {
    const mine: KnowledgeAsset[] = [];
    const rest: KnowledgeAsset[] = [];
    for (const source of sources) {
      (source.base_ids.includes(baseId) ? mine : rest).push(source);
    }
    return { inBase: mine, available: rest };
  }, [sources, baseId]);

  if (!base) {
    return (
      <div className="h-full overflow-y-auto p-8">
        {basesLoading ? (
          <Skeleton className="mx-auto h-40 max-w-3xl rounded-2xl" />
        ) : (
          <div className="mx-auto max-w-3xl">
            <EmptyState
              icon={Search}
              title="No such knowledge base"
              body="It may have been deleted, or the link may be wrong."
              action={
                <Button size="sm" onClick={() => router.push("/bases")}>
                  Back to knowledge bases
                </Button>
              }
            />
          </div>
        )}
      </div>
    );
  }

  async function detach(source: KnowledgeAsset) {
    try {
      upsert(await api.removeAssetFromBase(source.id, baseId));
    } catch {
      toast.error("Couldn't take that out of this base.");
    }
  }

  async function attach(source: KnowledgeAsset) {
    try {
      upsert(await api.addAssetToBase(source.id, baseId));
    } catch {
      toast.error("Couldn't file that into this base.");
    }
  }

  function openInChat() {
    if (base && !attachedIds.includes(base.id)) setAttached([...attachedIds, base.id]);
    router.push("/");
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="border-b border-border-soft bg-card px-6 py-5 md:px-8">
        <div className="mx-auto max-w-6xl">
          <Link
            href="/bases"
            className="mb-3 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" aria-hidden /> All knowledge bases
          </Link>

          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div className="flex min-w-0 items-center gap-3.5">
              <span
                aria-hidden
                className={cn(
                  "flex size-10 shrink-0 items-center justify-center rounded-xl text-lg font-bold text-white shadow-xs",
                  baseTileClass(base)
                )}
              >
                {baseInitial(base.name)}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="truncate text-display-sm font-semibold">{base.name}</h1>
                  <button
                    type="button"
                    onClick={() => setEditing(true)}
                    title="Edit this base"
                    aria-label="Edit this base"
                    className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    <Pencil className="size-3.5" aria-hidden />
                  </button>
                </div>
                <p className="mt-0.5 max-w-xl truncate text-xs text-muted-foreground">
                  {base.description || "No description."}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span
                draggable
                onDragStart={(event) => {
                  setBaseDragData(event, base.id);
                  setDragging(base.id);
                }}
                onDragEnd={() => setDragging(null)}
                title="Drag this onto the Chat tab"
                className="flex cursor-grab select-none items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-2 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary hover:text-primary active:cursor-grabbing"
              >
                <GripVertical className="size-3.5" aria-hidden /> Drag to Chat
              </span>
              <Button variant="secondary" size="md" onClick={openInChat}>
                <MessageSquare className="size-3.5" aria-hidden /> Open in chat
              </Button>
              <Button variant="secondary" size="md" onClick={() => setAttaching(true)}>
                <Link2 className="size-3.5" aria-hidden /> Attach from library
              </Button>
              <Button size="md" onClick={() => setUploading(true)}>
                <Plus className="size-3.5" aria-hidden /> Add a source
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto w-full max-w-6xl p-6 md:p-8">
        <div className="mb-4 flex items-center justify-between gap-4">
          <h2 className="text-sm font-semibold">Sources in this base ({inBase.length})</h2>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Only these are searched when this base is attached.
          </span>
        </div>

        {sourcesLoading && sources.length === 0 ? (
          <div className="space-y-2">
            {[0, 1, 2].map((key) => (
              <Skeleton key={key} className="h-14 rounded-xl" />
            ))}
          </div>
        ) : inBase.length === 0 ? (
          <EmptyState
            icon={Plus}
            title="Nothing filed here yet"
            body="Upload a source into this base, or file one you have already added."
            action={
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => setAttaching(true)}>
                  Attach from library
                </Button>
                <Button size="sm" onClick={() => setUploading(true)}>
                  Add a source
                </Button>
              </div>
            }
          />
        ) : (
          <ul className="space-y-2">
            {inBase.map((source) => (
              <li
                key={source.id}
                className="flex items-center gap-3 rounded-xl border border-border-soft bg-card p-3"
              >
                <SourceIcon type={source.source_type} />
                <Link href={`/sources/${source.id}`} className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium hover:underline">
                    {sourceTitle(source)}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {typeCopy[source.source_type]?.label ?? source.source_type}
                    {source.passage_count > 0 ? ` · ${source.passage_count} passages` : ""}
                    {source.base_ids.length > 1
                      ? ` · also in ${source.base_ids.length - 1} other base${
                          source.base_ids.length === 2 ? "" : "s"
                        }`
                      : ""}
                  </p>
                </Link>
                <StatusBadge status={source.status} />
                <button
                  type="button"
                  onClick={() => void detach(source)}
                  title={`Remove ${sourceTitle(source)} from ${base.name}`}
                  aria-label={`Remove ${sourceTitle(source)} from ${base.name}`}
                  className="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
                >
                  <X className="size-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing ? <BaseEditor base={base} onClose={() => setEditing(false)} /> : null}
      {uploading ? (
        <AddSourceDialog knowledgeBaseId={base.id} onClose={() => setUploading(false)} />
      ) : null}
      {attaching ? (
        <AttachFromLibrary
          baseName={base.name}
          available={available}
          onAttach={attach}
          onClose={() => setAttaching(false)}
        />
      ) : null}
    </div>
  );
}

function AttachFromLibrary({
  baseName,
  available,
  onAttach,
  onClose
}: {
  baseName: string;
  available: KnowledgeAsset[];
  onAttach: (source: KnowledgeAsset) => Promise<void>;
  onClose: () => void;
}) {
  const [filter, setFilter] = useState("");
  const needle = filter.trim().toLowerCase();
  const shown = needle
    ? available.filter((source) => sourceTitle(source).toLowerCase().includes(needle))
    : available;

  return (
    <Modal onClose={onClose} size="md">
      <ModalHeader>
        <div>
          <h2 className="text-sm font-semibold">Attach from your library</h2>
          <p className="text-[11px] text-muted-foreground">
            Files it into {baseName} without re-uploading or re-indexing it.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" aria-hidden />
        </button>
      </ModalHeader>

      <div className="border-b border-border-soft px-5 py-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground"
            aria-hidden
          />
          <input
            type="search"
            autoFocus
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Search your sources…"
            aria-label="Search your sources"
            className="w-full rounded-xl border border-transparent bg-muted py-2 pl-9 pr-3 text-xs placeholder:text-muted-foreground focus:border-primary focus:bg-card focus:outline-none"
          />
        </div>
      </div>

      <ModalBody className="space-y-1.5 p-3">
        {shown.length === 0 ? (
          <p className="px-2 py-8 text-center text-xs text-muted-foreground">
            {available.length === 0
              ? "Every source you have is already in this base."
              : "Nothing matches that."}
          </p>
        ) : (
          shown.map((source) => (
            <div
              key={source.id}
              className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted"
            >
              <SourceIcon type={source.source_type} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">{sourceTitle(source)}</p>
                <p className="text-[10px] text-muted-foreground">
                  {typeCopy[source.source_type]?.label ?? source.source_type}
                  {source.passage_count > 0 ? ` · ${source.passage_count} passages` : ""}
                </p>
              </div>
              <Button
                size="sm"
                variant="secondary"
                className="border-primary-soft-border bg-primary-soft text-primary"
                onClick={() => void onAttach(source)}
              >
                Attach
              </Button>
            </div>
          ))
        )}
      </ModalBody>

      <ModalFooter className="justify-end">
        <Button variant="secondary" size="sm" onClick={onClose}>
          Done
        </Button>
      </ModalFooter>
    </Modal>
  );
}
