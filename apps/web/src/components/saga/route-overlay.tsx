"use client";

import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { Modal, ModalBody, ModalHeader, type ModalPlacement, type ModalSize } from "@kb/ui";
import type { ReactNode } from "react";

/**
 * A route rendered as an overlay over the tab you were on.
 *
 * Closing is `router.back()`, not a state flip, because the overlay *is* a history entry —
 * it got here through a real navigation to a real URL. Anything else would leave the address
 * bar pointing at a panel that is no longer on screen, and make the browser's own Back button
 * do something different from the close button beside it.
 */
export function RouteOverlay({
  title,
  subtitle,
  children,
  size = "md",
  placement = "center",
  bodyClassName
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  size?: ModalSize;
  placement?: ModalPlacement;
  bodyClassName?: string;
}) {
  const router = useRouter();
  const close = () => router.back();

  return (
    <Modal onClose={close} size={size} placement={placement}>
      <ModalHeader>
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">{title}</h2>
          {subtitle ? (
            <p className="truncate text-[11px] text-muted-foreground">{subtitle}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={close}
          aria-label="Close"
          className="shrink-0 rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" aria-hidden />
        </button>
      </ModalHeader>
      <ModalBody {...(bodyClassName ? { className: bodyClassName } : {})}>{children}</ModalBody>
    </Modal>
  );
}

/**
 * The same content when the URL was opened cold — a shared link, a reload, a new tab.
 *
 * There is no page behind it to overlay, so it is a page: same panel, same width, centred on
 * the canvas under the real tab bar.
 */
export function RoutePage({
  title,
  description,
  children
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-5 py-8 md:px-8">
        <h1 className="text-display-sm font-semibold">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
        ) : null}
        <div className="mt-6">{children}</div>
      </div>
    </div>
  );
}
