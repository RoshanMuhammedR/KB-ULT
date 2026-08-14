import { buttonClass } from "@kb/ui";
import { SiteLayout } from "@/components/saga/site-chrome";

export default function NotFound() {
  return (
    <SiteLayout>
      <div className="mx-auto max-w-xl px-5 py-32 text-center">
        <h1 className="text-display-lg">Page not found</h1>
        <p className="mt-4 text-[16px] text-muted-foreground">
          The link may be out of date. Everything Saga does lives on one page — start there.
        </p>
        <a href="/" className={buttonClass("primary", "lg", "mt-8")}>
          Go home
        </a>
      </div>
    </SiteLayout>
  );
}
