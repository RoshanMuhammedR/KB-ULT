import Link from "next/link";
import { Logo } from "@kb/ui";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="saga-container site-footer__inner">
        <Logo />
        <div className="site-footer__links">
          <Link className="saga-navlink" href="/register">
            Get started
          </Link>
          <Link className="saga-navlink" href="/login">
            Log in
          </Link>
          <a className="saga-navlink" href="mailto:hello@saga.dev">
            hello@saga.dev
          </a>
        </div>
        <span className="site-footer__legal saga-meta">© {new Date().getFullYear()} Saga</span>
      </div>
    </footer>
  );
}
