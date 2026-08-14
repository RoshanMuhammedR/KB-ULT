"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "@kb/ui";

type ToastKind = "error" | "success" | "info";
type Toast = { id: number; kind: ToastKind; message: string };

type ToastValue = {
  push: (message: string, kind?: ToastKind) => void;
  error: (message: string) => void;
  success: (message: string) => void;
};

const ToastContext = createContext<ToastValue | null>(null);
let seq = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const push = useCallback(
    (message: string, kind: ToastKind = "info") => {
      const id = ++seq;
      setToasts((t) => [...t, { id, kind, message }]);
      setTimeout(() => dismiss(id), 5000);
    },
    [dismiss]
  );

  const value = useMemo<ToastValue>(
    () => ({
      push,
      error: (m) => push(m, "error"),
      success: (m) => push(m, "success")
    }),
    [push]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
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
    </ToastContext.Provider>
  );
}

export function useToast(): ToastValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
