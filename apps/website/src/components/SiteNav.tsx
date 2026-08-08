import Link from "next/link";
import { Logo, buttonClass } from "@kb/ui";
import { LOGIN_URL, REGISTER_URL } from "@/lib/config";

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
        {/* Plain anchors: auth lives in the product app, which is a separate Next app. */}
        <div className="site-nav__actions">
          <a className={buttonClass({ variant: "ghost", size: "sm" })} href={LOGIN_URL}>
            Log in
          </a>
          <a className={buttonClass({ variant: "primary", size: "sm" })} href={REGISTER_URL}>
            Get started
          </a>
        </div>
      </div>
    </header>
  );
}
