import { AppData } from "@/components/saga/app-data";
import { AppShell } from "@/components/saga/app-shell";
import { OnboardingProvider } from "@/components/saga/onboarding";
import { RequireAuth } from "@/components/saga/require-auth";

/**
 * Everything behind the sign-in wall. /login and /register sit outside this group, so they
 * render without the shell and without waiting on the library to load.
 *
 * `modal` is a parallel route slot. Routes that read as overlays — the memory drawer, the
 * account panel, the source reader — are still real, addressable pages; navigating to one
 * from inside the app renders it in this slot *on top of* whatever tab you were on, and
 * opening the same URL cold renders the page on its own. That is what keeps "/sources/{id}
 * is a link you can send someone" and "it opens over the conversation" from being a choice
 * between two things.
 */
export default function AppLayout({
  children,
  modal
}: {
  children: React.ReactNode;
  modal: React.ReactNode;
}) {
  return (
    <RequireAuth>
      <AppData />
      <OnboardingProvider>
        <AppShell>{children}</AppShell>
        {modal}
      </OnboardingProvider>
    </RequireAuth>
  );
}
