import { AppData } from "@/components/saga/app-data";
import { AppShell } from "@/components/saga/app-shell";
import { RequireAuth } from "@/components/saga/require-auth";

/**
 * Everything behind the sign-in wall. /login and /register sit outside this group, so they
 * render without the shell and without waiting on the library to load.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <AppData />
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}
