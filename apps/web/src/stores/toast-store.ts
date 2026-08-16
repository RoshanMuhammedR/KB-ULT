"use client";

import { create } from "zustand";

export type ToastKind = "error" | "success" | "info";
export type Toast = { id: number; kind: ToastKind; message: string };

const DISMISS_AFTER_MS = 5000;

let seq = 0;
// Held so a manual dismiss can cancel the auto-dismiss; the provider version left every timer
// to fire into an already-empty list five seconds later.
const timers = new Map<number, ReturnType<typeof setTimeout>>();

type ToastState = {
  toasts: Toast[];
  push: (message: string, kind?: ToastKind) => void;
  error: (message: string) => void;
  success: (message: string) => void;
  dismiss: (id: number) => void;
};

export const useToastStore = create<ToastState>()((set, get) => ({
  toasts: [],

  push: (message, kind = "info") => {
    const id = ++seq;
    set((state) => ({ toasts: [...state.toasts, { id, kind, message }] }));
    timers.set(
      id,
      setTimeout(() => get().dismiss(id), DISMISS_AFTER_MS)
    );
  },

  error: (message) => get().push(message, "error"),
  success: (message) => get().push(message, "success"),

  dismiss: (id) => {
    const timer = timers.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.delete(id);
    }
    // Return the same state when there is nothing to remove, so a double dismiss (timer and
    // click racing) does not notify subscribers twice.
    set((state) =>
      state.toasts.some((toast) => toast.id === id)
        ? { toasts: state.toasts.filter((toast) => toast.id !== id) }
        : state
    );
  }
}));

/**
 * Raise a toast from anywhere — a component, a store action, a poll loop.
 *
 * Deliberately not a hook: a component that only *raises* toasts has no reason to subscribe
 * to the list and re-render whenever one appears. `push` stays internal because nothing ever
 * called it directly.
 */
export const toast = {
  error: (message: string) => useToastStore.getState().error(message),
  success: (message: string) => useToastStore.getState().success(message)
};
