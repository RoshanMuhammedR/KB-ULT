"use client";

import { useEffect } from "react";
import { initClientStores } from "@/stores/session-lifecycle";

/**
 * Reads the session cookie after hydration, never during render — so the server HTML
 * (status "loading", and RequireAuth's spinner) and the first client render still agree.
 */
export function StoreBootstrap(): null {
  useEffect(() => {
    initClientStores();
  }, []);
  return null;
}
