"use client";

import { useParams, useRouter } from "next/navigation";
import { X } from "lucide-react";
import { Modal, ModalHeader } from "@kb/ui";
import { SourceDetail } from "@/components/saga/source-detail";
import { useOverlayOpen } from "@/components/saga/route-overlay";

/**
 * The source reader, over the conversation that sent you to it.
 *
 * Wide rather than centred-narrow: this is a document being read, not a form being filled,
 * and the citations panel needs room beside it.
 */
export default function SourceOverlay() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const router = useRouter();
  const open = useOverlayOpen(`/sources/${sourceId}`);
  const close = () => router.back();

  if (!open) return null;

  return (
    <Modal onClose={close} size="xl">
      {/* A header bar rather than a close button floating over the content. The panel below
          has a heading and a row of actions of its own at exactly that corner, and an
          absolutely-positioned button landed on top of both. */}
      <ModalHeader>
        <h2 className="truncate text-sm font-semibold">Source</h2>
        <button
          type="button"
          onClick={close}
          aria-label="Close"
          className="shrink-0 rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" aria-hidden />
        </button>
      </ModalHeader>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <SourceDetail sourceId={sourceId} inOverlay />
      </div>
    </Modal>
  );
}
