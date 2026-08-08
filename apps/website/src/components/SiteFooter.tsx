import { Logo } from "@kb/ui";
import { LOGIN_URL, REGISTER_URL } from "@/lib/config";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="saga-container site-footer__inner">
        <Logo />
        <div className="site-footer__links">
          <a className="saga-navlink" href={REGISTER_URL}>
            Get started
          </a>
          <a className="saga-navlink" href={LOGIN_URL}>
            Log in
          </a>
          <a className="saga-navlink" href="mailto:hello@saga.dev">
            hello@saga.dev
          </a>
        </div>
        <span className="site-footer__legal saga-meta">© {new Date().getFullYear()} Saga</span>
      </div>
    </footer>
  );
}
