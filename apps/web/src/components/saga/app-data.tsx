"use client";

import { useEffect } from "react";
import { useConversationsStore } from "@/stores/conversations-store";
import { useSourcesStore } from "@/stores/sources-store";

/**
 * Kicks the app's initial fetches.
 *
 * Mounted inside <RequireAuth>, so it can only run once there is a session — which is exactly
 * the gating the providers used to get for free by being nested inside it. Doing it here
 * rather than inside the stores keeps them from having to know about auth, which would be an
 * import cycle.
 */
export function AppData(): null {
  useEffect(() => {
    void useSourcesStore.getState().ensureLoaded();
    void useConversationsStore.getState().ensureLoaded();
  }, []);
  return null;
}
