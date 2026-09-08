"use client";

import { useEffect } from "react";
import { useConversationsStore } from "@/stores/conversations-store";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
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
    // Bases first in intent, not in order: the header states a count and the composer
    // names what it is answering from, so both are wanted on every screen rather than only
    // on the ones that list bases.
    void useKnowledgeBasesStore.getState().ensureLoaded();
    void useSourcesStore.getState().ensureLoaded();
    void useConversationsStore.getState().ensureLoaded();
  }, []);
  return null;
}
