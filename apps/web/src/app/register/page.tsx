"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Logo } from "@kb/ui";

const WEBSITE_URL = process.env.NEXT_PUBLIC_WEBSITE_URL ?? "";

// Registration lives on the marketing site (a new workspace can't be created from inside an
// existing tenant domain). Bounce there; fall back to the local login if it isn't configured.
export default function RegisterRedirect() {
  const router = useRouter();

  useEffect(() => {
    if (WEBSITE_URL) {
      window.location.replace(`${WEBSITE_URL}/register`);
    } else {
      router.replace("/login");
    }
  }, [router]);

  return (
    <div className="auth__center">
      <div className="bootstrap">
        <Logo />
        <div className="spinner" />
        <h1>Taking you to sign up…</h1>
      </div>
    </div>
  );
}
