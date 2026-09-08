"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";
import { Panel, cn } from "@kb/ui";
import type { KnowledgeAsset } from "@/types/api";
import { baseDotClass } from "@/lib/base-colour";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { useSourcesStore } from "@/stores/sources-store";
import { toast } from "@/stores/toast-store";
import * as api from "@/lib/api";

/**
 * Which bases a source is filed in, and a control to change that.
 *
 * A source in no base is a real, allowed state — it is still the user's file, it is just not
 * searched. Saying "Not in any base" out loud is the point: silence would read as a rendering
 * bug rather than as the thing it is.
 */
export function SourceBases({ source, className }: { source: KnowledgeAsset; className?: string }) {
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const upsert = useSourcesStore((state) => state.upsert);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const members = bases.filter((base) => source.base_ids.includes(base.id));
  const rest = bases.filter((base) => !source.base_ids.includes(base.id));

  async function change(action: Promise<KnowledgeAsset>, failure: string) {
    setBusy(true);
    try {
      upsert(await action);
    } catch {
      toast.error(failure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn("relative flex flex-wrap items-center gap-1.5", className)}>
      {members.length === 0 ? (
        <span className="text-[11px] text-muted-soft">Not in any base — nothing searches it</span>
      ) : (
        members.map((base) => (
          <span
            key={base.id}
            className="group inline-flex items-center gap-1.5 rounded-full border border-border bg-muted py-0.5 pl-2 pr-1 text-[11px] font-medium"
          >
            <span aria-hidden className={cn("size-2 rounded-full", baseDotClass(base))} />
            {base.name}
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void change(
                  api.removeAssetFromBase(source.id, base.id),
                  "Couldn't take that out of the base."
                )
              }
              title={`Remove from ${base.name}`}
              aria-label={`Remove from ${base.name}`}
              className="rounded-full p-0.5 text-muted-soft hover:bg-surface-strong hover:text-destructive"
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
        ))
      )}

      {rest.length > 0 ? (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-haspopup="menu"
          className="inline-flex items-center gap-1 rounded-full border border-dashed border-border-strong px-2 py-0.5 text-[11px] font-medium text-muted-foreground hover:border-primary hover:text-primary"
        >
          <Plus className="size-3" aria-hidden /> File it
        </button>
      ) : null}

      {open ? (
        <>
          {/* Click-away. A plain overlay rather than a focus trap: this is a menu, and what is
              behind it stays readable while it is open. */}
          <button
            type="button"
            aria-label="Close"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <Panel className="absolute left-0 top-full z-20 mt-1 w-56 p-1 shadow-lg">
            <ul role="menu" className="max-h-56 overflow-y-auto">
              {rest.map((base) => (
                <li key={base.id}>
                  <button
                    type="button"
                    role="menuitem"
                    disabled={busy}
                    onClick={() => {
                      setOpen(false);
                      void change(
                        api.addAssetToBase(source.id, base.id),
                        "Couldn't file that into the base."
                      );
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
