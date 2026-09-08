"use client";

import { AccountPanel } from "@/components/saga/account-panel";
import { RouteOverlay } from "@/components/saga/route-overlay";

export default function AccountOverlay() {
  return (
    <RouteOverlay href="/account" title="Account" subtitle="Your account and your library" size="sm">
      <AccountPanel />
    </RouteOverlay>
  );
}
