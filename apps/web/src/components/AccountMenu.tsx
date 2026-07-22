"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

export function AccountMenu() {
  const { session, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const email = session?.email ?? "";
  const domain = session?.domain ?? "";
  const name = session?.name || domain;
  const initial = (name[0] ?? email[0] ?? "?").toUpperCase();

  return (
    <div className="acct" ref={ref}>
      <button
        className="acct__chip"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="acct__avatar">{initial}</span>
        <span className="acct__domain">{domain || "workspace"}</span>
        <ChevronDown size={14} />
      </button>
      {open ? (
        <div className="acct__menu" role="menu">
          <div className="acct__head">
            <span className="acct__name">{name || "Your workspace"}</span>
            {email ? <span className="acct__sub">{email}</span> : null}
            {domain ? <span className="acct__sub">{domain}</span> : null}
          </div>
          <button className="acct__signout" role="menuitem" onClick={() => void logout()}>
            <LogOut size={15} strokeWidth={1.5} />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
