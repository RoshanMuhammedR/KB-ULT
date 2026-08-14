import { Logo, Pill } from "@kb/ui";

const WEBSITE_URL = process.env.NEXT_PUBLIC_WEBSITE_URL ?? "/";

/**
 * The two signed-out screens. The logo links back to the marketing site with a plain <a>,
 * because next/link would prefix it with this app's /app basePath.
 */
export function AuthShell({
  asideTitle,
  asideSub,
  children
}: {
  asideTitle: string;
  asideSub: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-dvh md:grid md:grid-cols-2">
      <aside className="hidden flex-col justify-between border-r border-border bg-canvas-soft p-10 md:flex">
        <a href={WEBSITE_URL} aria-label="Saga">
          <Logo />
        </a>
        <div className="max-w-md">
          <h2 className="text-display-lg">{asideTitle}</h2>
          <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">{asideSub}</p>
          <div className="mt-6">
            <Pill>Private · Source-cited</Pill>
          </div>
        </div>
        <p className="text-[12px] text-muted-soft">
          © {new Date().getFullYear()} Saga
        </p>
      </aside>

      <main className="flex items-center justify-center p-6 md:p-10">
        <div className="w-full max-w-sm">
          <a href={WEBSITE_URL} aria-label="Saga" className="mb-8 inline-flex md:hidden">
            <Logo />
          </a>
          {children}
        </div>
      </main>
    </div>
  );
}
