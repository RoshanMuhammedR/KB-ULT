"use client";

import { useId, useRef } from "react";
import { Button } from "./button";
import type { ButtonVariant } from "./button";
import { Modal } from "./modal";

/**
 * Replaces `window.confirm` for destructive actions. Render it conditionally — it has no
 * internal open state.
 *
 * The scrim, focus trap, Escape and scroll lock all come from `Modal`; this is the wording
 * and the two buttons. Focus lands on the confirm button rather than the first focusable
 * element, so Enter does the thing the dialog was opened to do.
 */
export function ConfirmDialog({
  title,
  body,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  confirmVariant = "danger",
  busy = false,
  onConfirm,
  onCancel
}: {
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: ButtonVariant;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const confirmRef = useRef<HTMLButtonElement | null>(null);
  const titleId = useId();
  const bodyId = useId();

  return (
    <Modal
      onClose={onCancel}
      size="sm"
      labelledBy={titleId}
      describedBy={bodyId}
      initialFocus={confirmRef}
      className="rounded-lg"
    >
      <div className="p-6">
        <h2 id={titleId} className="text-display-sm">
          {title}
        </h2>
        <p id={bodyId} className="mt-2 text-sm text-muted-foreground">
          {body}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            ref={confirmRef}
            variant={confirmVariant}
            size="sm"
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Working…" : confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
