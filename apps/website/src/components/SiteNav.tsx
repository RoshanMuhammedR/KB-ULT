import Link from "next/link";
import { Logo, buttonClass } from "@kb/ui";

/** Transparent top bar floating over the obsidian canvas, closed by a 1px graphite rule. */
export function SiteNav() {
  return (
    <header className="site-nav">
      <div className="saga-container site-nav__inner">
        <Link href="/" aria-label="Saga home">
          <Logo />
        </Link>
        <nav className="site-nav__links" aria-label="Primary">
          <Link className="saga-navlink" href="/#how">
            How it works
          </Link>
          <Link className="saga-navlink" href="/#features">
            Features
          </Link>
        </nav>
        <div className="site-nav__actions">
          <Link className={buttonClass({ variant: "ghost", size: "sm" })} href="/login">
            Log in
          </Link>
          <Link className={buttonClass({ variant: "primary", size: "sm" })} href="/register">
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}
