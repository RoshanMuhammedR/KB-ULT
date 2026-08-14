import { Logo, buttonClass } from "@kb/ui";
import { LOGIN_URL, REGISTER_URL } from "@/lib/config";

/**
 * One page, so the header carries no navigation — just the two conversion paths. Both are
 * plain anchors because they cross into the product app's /app basePath, which next/link
 * would rewrite.
 */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
        <a href="/" aria-label="Saga">
          <Logo />
        </a>
        <div className="flex items-center gap-2">
          <a href={LOGIN_URL} className={buttonClass("ghost", "sm")}>
            Log in
          </a>
          <a href={REGISTER_URL} className={buttonClass("primary", "sm")}>
            Create your account
          </a>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-10">
        <Logo />
        <p className="max-w-md text-[13px] leading-relaxed text-muted-foreground">
          Saga turns your own documents, decks, notes, recordings and videos into a private,
          source-cited knowledge base you can ask questions of.
        </p>
        <p className="text-[12px] text-muted-soft">
          © {new Date().getFullYear()} Saga. Your library, isolated at the database.
        </p>
      </div>
    </footer>
  );
}

export function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <SiteHeader />
      <main>{children}</main>
      <SiteFooter />
    </div>
  );
}
