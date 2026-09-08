"use client";

import { useEffect, useState } from "react";
import { LibraryBig, Plus, Search } from "lucide-react";
import { sourceTitle, typeCopy, type SourceType } from "@kb/shared";
import { Button, ConfirmDialog, EmptyState, Input, Panel, Skeleton, cn } from "@kb/ui";
import { AddSourceDialog } from "@/components/saga/add-source-dialog";
import { SourceRow } from "@/components/saga/source-row";
import type { KnowledgeAsset } from "@/types/api";
import * as api from "@/lib/api";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { useSourcesStore } from "@/stores/sources-store";
import { baseDotClass } from "@/lib/base-colour";
import { toast } from "@/stores/toast-store";

const TYPE_FILTERS: (SourceType | "all")[] = ["all", "pdf", "youtube", "markdown", "pptx", "audio"];
const STATUS_FILTERS: { key: "all" | "ready" | "working" | "failed"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "ready", label: "Ready" },
  { key: "working", label: "Being prepared" },
  { key: "failed", label: "Needs attention" }
];

export default function LibraryPage() {
  const sources = useSourcesStore((state) => state.sources);
  const loading = useSourcesStore((state) => state.loading);
  const counts = useSourcesStore((state) => state.counts);
  const track = useSourcesStore((state) => state.track);
  const ensureSources = useSourcesStore((state) => state.ensureLoaded);
  const remove = useSourcesStore((state) => state.remove);
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const ensureBases = useKnowledgeBasesStore((state) => state.ensureLoaded);
  const [query, setQuery] = useState("");
  const [type, setType] = useState<SourceType | "all">("all");
  const [status, setStatus] = useState<"all" | "ready" | "working" | "failed">("all");
  // "" is every base, including sources filed in none. A base id narrows to that base only.
  const [base, setBase] = useState("");
  const [adding, setAdding] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<KnowledgeAsset | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    void ensureBases();
    void ensureSources();
  }, [ensureBases, ensureSources]);

  const needle = query.trim().toLowerCase();
  const filtered = sources.filter((source) => {
    if (needle && !`${sourceTitle(source)} ${source.filename}`.toLowerCase().includes(needle)) {
      return false;
    }
    if (base && !source.base_ids.includes(base)) return false;
    if (type !== "all" && source.source_type !== type) return false;
    if (status === "ready" && source.status !== "ready") return false;
    if (status === "failed" && source.status !== "failed") return false;
    if (status === "working" && (source.status === "ready" || source.status === "failed")) {
      return false;
    }
    return true;
  });

  async function retry(source: KnowledgeAsset) {
    try {
      // The worker re-downloads the original, so this never needs a re-upload.
      track(await api.retryAsset(source.id));
    } catch {
      toast.error("Couldn't start that again. Try once more in a moment.");
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.deleteAsset(pendingDelete.id);
      remove(pendingDelete.id);
      setPendingDelete(null);
    } catch {
      toast.error("Couldn't remove that source.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="border-b border-border-soft bg-card px-6 py-6 md:px-8">
        <div className="mx-auto flex max-w-6xl flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-display-sm font-semibold tracking-tight">Document library</h1>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Everything you have added, across every base. {counts.ready} ready to answer from
              {counts.total === counts.ready ? "" : ` · ${counts.total} in total`}.
            </p>
          </div>
          <Button size="sm" className="shrink-0" onClick={() => setAdding(true)}>
            <Plus className="size-4" aria-hidden /> Add a source
          </Button>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-5 py-6 md:px-8">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-56 flex-1">
            <Search
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-soft"
              aria-hidden
            />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search your library"
              placeholder="Search by title or filename"
              className="h-10 pl-9 text-sm"
            />
          </div>
          {bases.length > 1 ? (
            <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by knowledge base">
              <FilterChip active={base === ""} onClick={() => setBase("")}>
                All bases
              </FilterChip>
              {bases.map((option) => (
                <FilterChip
                  key={option.id}
                  active={base === option.id}
                  onClick={() => setBase(option.id)}
                >
                  <span aria-hidden className={cn("size-2 rounded-full", baseDotClass(option))} />
                  {option.name}
                </FilterChip>
              ))}
            </div>
          ) : null}
          <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by type">
            {TYPE_FILTERS.map((option) => (
              <FilterChip key={option} active={type === option} onClick={() => setType(option)}>
                {option === "all" ? "All types" : typeCopy[option].label}
              </FilterChip>
            ))}
          </div>
          <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by status">
            {STATUS_FILTERS.map((option) => (
              <FilterChip
                key={option.key}
                active={status === option.key}
                onClick={() => setStatus(option.key)}
              >
                {option.label}
              </FilterChip>
            ))}
          </div>
        </div>

        <div className="mt-6 space-y-3">
          {loading ? (
            [0, 1, 2].map((index) => (
              <Panel key={index} className="flex items-center gap-4 p-4">
                <Skeleton className="size-9 rounded-md" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="w-1/3" />
                  <Skeleton className="w-1/4" />
                </div>
              </Panel>
            ))
          ) : sources.length === 0 ? (
            <EmptyState
              icon={LibraryBig}
              title="Your library is empty"
              body="Saga can only answer from material you've added. Start with one PDF — it takes about ten seconds and you'll be asking questions of it a moment later."
              action={<Button onClick={() => setAdding(true)}>Add your first source</Button>}
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Search}
              title="Nothing matches those filters"
              body="Try a different search term, or clear the type and status filters to see the whole library again."
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setQuery("");
                    setType("all");
                    setStatus("all");
                    setBase("");
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            filtered.map((source) => (
              <SourceRow
                key={source.id}
                source={source}
                onRetry={(target) => void retry(target)}
                onDelete={setPendingDelete}
              />
            ))
          )}
        </div>
      </div>

      {adding ? (
        <AddSourceDialog onClose={() => setAdding(false)} />
      ) : null}

      {pendingDelete ? (
        <ConfirmDialog
          title="Remove this source?"
          body={`“${sourceTitle(pendingDelete)}” and everything indexed from it will be deleted. Answers already given will keep their quotes, but nothing new can cite it.`}
          confirmLabel="Remove source"
          busy={deleting}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setPendingDelete(null)}
        />
      ) : null}
    </div>
  );
}

/** One filter chip. Same shape for type, status and base, so they read as one control. */
function FilterChip({
  active,
  onClick,
  children
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-[13px] font-medium transition-colors",
        active
          ? "border-primary bg-primary-soft text-primary"
          : "border-border bg-card text-muted-foreground hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}
