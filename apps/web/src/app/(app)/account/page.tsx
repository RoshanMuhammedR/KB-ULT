"use client";

import { useState } from "react";
import { Button, Label, Panel } from "@kb/ui";
import { AppHeader } from "@/components/saga/app-shell";
import { useAuth } from "@/lib/auth-context";
import { useSources } from "@/lib/sources-context";

export default function AccountPage() {
  const { session, logout } = useAuth();
  const { counts } = useSources();
  const [signingOut, setSigningOut] = useState(false);

  return (
    <div>
      <AppHeader title="Account" description="Your account and your library." />

      <div className="grid max-w-3xl gap-6 px-5 py-6 md:px-8">
        <Panel className="p-5">
          <Label>Signed in as</Label>
          <p className="mt-2 text-[15px] font-semibold">{session?.email ?? "—"}</p>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Email and password, or Google. There are no plans to pick and nothing to configure.
          </p>
        </Panel>

        <Panel className="p-5">
          <Label>Your material stays here</Label>
          <p className="mt-2 text-[14px] leading-relaxed text-muted-foreground">
            Your library is private to you. Sources, passages and conversations are isolated at
            the database level, nobody else can be added, and none of it is used to train models.
          </p>
          <p className="mt-3 text-[13px] text-muted-foreground">
            {counts.total} {counts.total === 1 ? "source" : "sources"} · {counts.ready} ready to
            answer from
          </p>
        </Panel>

        <Panel className="p-5">
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
              void logout();
            }}
          >
            {signingOut ? "Signing out…" : "Sign out"}
          </Button>
        </Panel>
      </div>
    </div>
  );
}
