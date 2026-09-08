"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "../cn";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The scroll lock, counted.
 *
 * Module-scoped because the lock is a property of the document, not of any one dialog. Two
 * stacked modals — a confirm inside an overlay, say — each capture and restore what they
 * found, and whichever cleans up last wins. React does not promise that is the inner one, so
 * the outer modal could restore "" first and the inner one then put "hidden" back, leaving
 * the whole page permanently unscrollable with nothing on screen to explain why.
 *
 * A counter has no ordering to get wrong: the last release restores, whoever it is.
 */
let locks = 0;
let restore = "";

function lockScroll(): () => void {
  if (locks === 0) {
    restore = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  locks += 1;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    locks -= 1;
    if (locks === 0) document.body.style.overflow = restore;
  };
}

/**
 * Which dialog is on top.
 *
 * Every open modal listens on `document` for Escape and Tab, so a confirm opened inside an
 * overlay had two listeners answering the same key: Escape cancelled the confirm *and* closed
 * the overlay underneath it, and Tab was fought over by two focus traps. Only the topmost
 * dialog should hear either.
 *
 * A module-level stack rather than an event-bubbling trick, because these listeners are on
 * the document and there is no DOM nesting between two `fixed` panels to bubble through.
 */
const stack: symbol[] = [];

function pushDialog(token: symbol): () => void {
  stack.push(token);
  return () => {
    const at = stack.lastIndexOf(token);
    if (at !== -1) stack.splice(at, 1);
  };
}

function isTopDialog(token: symbol): boolean {
  return stack[stack.length - 1] === token;
}

export type ModalSize = "sm" | "md" | "lg" | "xl" | "full";
export type ModalPlacement = "center" | "right";

const SIZES: Record<ModalSize, string> = {
  sm: "max-w-md",
  md: "max-w-xl",
  lg: "max-w-3xl",
  xl: "max-w-5xl",
  full: "max-w-[min(1400px,96vw)]"
};

/**
 * The one modal shell: scrim, focus trap, Escape, scroll lock, focus restore.
 *
 * Render it conditionally — like `ConfirmDialog` it holds no open state, because the thing
 * that knows whether a dialog is open is usually the router, and a component with its own
 * copy of that would drift from the URL the moment someone pressed Back.
 *
 * `placement="right"` makes it a drawer instead of a centred panel. Same trap, same
 * behaviour; only where it sits changes, so a drawer never needs a second implementation of
 * any of this.
 */
export function Modal({
  onClose,
  children,
  size = "md",
  placement = "center",
  labelledBy,
  describedBy,
  className,
  initialFocus,
  dismissable = true
}: {
  onClose: () => void;
  children: ReactNode;
  size?: ModalSize;
  placement?: ModalPlacement;
  labelledBy?: string;
  describedBy?: string;
  className?: string;
  /** Focused on open. Defaults to the first focusable thing in the panel. */
  initialFocus?: React.RefObject<HTMLElement | null>;
  /** Off for a dialog mid-work, where a stray backdrop click would lose what was typed. */
  dismissable?: boolean;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  // Read through a ref inside the key handler so a caller passing an inline arrow does not
  // tear down and rebuild the listener — and the scroll lock with it — on every render.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const dismissableRef = useRef(dismissable);
  dismissableRef.current = dismissable;

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const target =
      initialFocus?.current ?? panel?.querySelector<HTMLElement>(FOCUSABLE) ?? panel ?? null;
    target?.focus?.();

    const token = Symbol("modal");
    const pop = pushDialog(token);

    function onKeyDown(event: KeyboardEvent) {
      // A dialog with something open on top of it is not the one being typed into.
      if (!isTopDialog(token)) return;
      if (event.key === "Escape" && dismissableRef.current) {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const current = panelRef.current;
      if (!current) return;
      const focusable = Array.from(current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => element.offsetParent !== null || element === document.activeElement
      );
      if (focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      // Wrap at both ends so Tab can never escape the dialog.
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    const unlock = lockScroll();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      pop();
      unlock();
      previouslyFocused?.focus?.();
    };
    // `initialFocus` is read once, on open, deliberately: re-running this would re-lock
    // scrolling and steal focus back from whatever the user has since tabbed to.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex bg-foreground/30 backdrop-blur-[2px]",
        placement === "center" ? "items-center justify-center p-4" : "justify-end"
      )}
      onMouseDown={(event) => {
        if (dismissable && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        {...(labelledBy ? { "aria-labelledby": labelledBy } : {})}
        {...(describedBy ? { "aria-describedby": describedBy } : {})}
        tabIndex={-1}
        className={cn(
          "flex flex-col overflow-hidden border border-border bg-card shadow-2xl outline-none",
          placement === "center"
            ? cn("max-h-[92dvh] w-full rounded-2xl", SIZES[size])
            : cn("h-dvh w-full border-y-0 border-r-0 sm:w-[420px]", "rounded-none"),
          "motion-safe:animate-in motion-safe:fade-in",
          className
        )}
      >
        {children}
      </div>
    </div>
  );
}

/** The tinted strip at the top of a modal: title on the left, controls on the right. */
export function ModalHeader({
  children,
  className
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-between gap-3 border-b border-border-soft bg-background px-5 py-3.5",
        className
      )}
    >
      {children}
    </div>
  );
}

/** The scrolling middle. Everything long goes in here so the header and footer stay put. */
export function ModalBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("min-h-0 flex-1 overflow-y-auto p-5", className)}>{children}</div>;
}

export function ModalFooter({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-between gap-3 border-t border-border-soft bg-background px-5 py-3.5",
        className
      )}
    >
      {children}
    </div>
  );
}
