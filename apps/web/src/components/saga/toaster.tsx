"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "@kb/ui";
import { useToastStore } from "@/stores/toast-store";

/**
 * The toast viewport. Lives at the root rather than inside the (app) group, because /login
 * and /register raise toasts too.
 */
export function Toaster() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);

  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:items-end"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={cn(
            "hairline-panel pointer-events-auto flex w-full max-w-sm items-start gap-3 p-3 shadow-md",
            t.kind === "error" && "border-destructive/40"
          )}
        >
          <span
            aria-hidden
            className={cn(
              "mt-0.5 shrink-0",
              t.kind === "error"
                ? "text-destructive"
                : t.kind === "success"
                  ? "text-success"
                  : "text-muted-foreground"
            )}
          >
            {t.kind === "error" ? (
              <AlertCircle size={16} strokeWidth={1.5} />
            ) : t.kind === "success" ? (
              <CheckCircle2 size={16} strokeWidth={1.5} />
            ) : (
              <Info size={16} strokeWidth={1.5} />
            )}
          </span>
          <span className="flex-1 text-sm">{t.message}</span>
          <button
            type="button"
            className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Dismiss"
            onClick={() => dismiss(t.id)}
          >
            <X size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}
