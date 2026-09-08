"use client";

import { useParams, useRouter } from "next/navigation";
import { X } from "lucide-react";
import { Modal } from "@kb/ui";
import { SourceDetail } from "@/components/saga/source-detail";

/**
 * The source reader, over the conversation that sent you to it.
 *
 * Wide rather than centred-narrow: this is a document being read, not a form being filled,
 * and the citations panel needs room beside it.
 */
export default function SourceOverlay() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const router = useRouter();

  return (
    <Modal onClose={() => router.back()} size="xl" className="max-h-[92dvh]">
      <div className="relative min-h-0 flex-1 overflow-y-auto">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="Close"
          className="absolute right-3 top-3 z-10 rounded-full border border-border bg-card p-1.5 text-muted-foreground shadow-xs hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" aria-hidden />
        </button>
        <SourceDetail sourceId={sourceId} />
      </div>
    </Modal>
  );
}
