import Link from "next/link";
import { Logo, buttonClass } from "@kb/ui";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <Logo />
      <h1 className="mt-8 text-display-md">This page isn&apos;t here</h1>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        The link may be out of date, or the thing it pointed at was removed.
      </p>
      <Link href="/" className={buttonClass("primary", "md", "mt-6")}>
        Back to your library
      </Link>
    </div>
  );
}
