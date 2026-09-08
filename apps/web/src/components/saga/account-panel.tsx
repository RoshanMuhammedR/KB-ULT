"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Label, Panel } from "@kb/ui";
import { useAuthStore } from "@/stores/auth-store";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { useSourcesStore } from "@/stores/sources-store";

/** Who you are signed in as, what you have, and how to leave. Nothing to configure. */
export function AccountPanel() {
  const email = useAuthStore((state) => state.session?.email ?? null);
  const logout = useAuthStore((state) => state.logout);
  const router = useRouter();
  const counts = useSourcesStore((state) => state.counts);
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const [signingOut, setSigningOut] = useState(false);

  return (
    <div className="grid gap-5">
      <Panel className="border-border-soft p-5">
        <Label>Signed in as</Label>
        <p className="mt-2 text-[15px] font-semibold">{email ?? "—"}</p>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Email and password, or Google. There are no plans to pick and nothing to configure.
        </p>
      </Panel>

      <Panel className="border-border-soft p-5">
        <Label>Your material stays here</Label>
        <p className="mt-2 text-[14px] leading-relaxed text-muted-foreground">
          Your library is private to you. Sources, passages and conversations are isolated at
          the database level, nobody else can be added, and none of it is used to train models.
        </p>
        <p className="mt-3 text-[13px] text-muted-foreground">
          {counts.total} {counts.total === 1 ? "source" : "sources"} · {counts.ready} ready to
          answer from · {bases.length} {bases.length === 1 ? "base" : "bases"}
        </p>
      </Panel>

      <Panel className="border-border-soft p-5">
        <Label>Sign out</Label>
        <p className="mt-2 text-[14px] text-muted-foreground">
          Ends this session on this device. Your library is untouched.
        </p>
        <Button
          variant="secondary"
          className="mt-4"
          disabled={signingOut}
          onClick={() => {
            setSigningOut(true);
            // RequireAuth would bounce us anyway once status flips to "anon"; navigating
            // here just says so out loud rather than relying on a side effect.
            void logout().then(() => router.replace("/login"));
          }}
        >
          {signingOut ? "Signing out…" : "Sign out"}
        </Button>
      </Panel>
    </div>
  );
}
