"use client";

import { AppShell } from "@/components/saga/app-shell";
import { RequireAuth } from "@/lib/auth-context";
import { ConversationsProvider } from "@/lib/conversations-context";
import { SourcesProvider } from "@/lib/sources-context";

/**
 * Everything behind the sign-in wall. /login and /register sit outside this group, so they
 * render without the shell and without waiting on the library to load.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <SourcesProvider>
        <ConversationsProvider>
          <AppShell>{children}</AppShell>
        </ConversationsProvider>
      </SourcesProvider>
    </RequireAuth>
  );
}
