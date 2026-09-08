"use client";

import { AccountPanel } from "@/components/saga/account-panel";
import { RoutePage } from "@/components/saga/route-overlay";

/** /account opened cold. From inside the app it renders as a dialog instead — see @modal. */
export default function AccountPage() {
  return (
    <RoutePage title="Account" description="Your account and your library.">
      <AccountPanel />
    </RoutePage>
  );
}
