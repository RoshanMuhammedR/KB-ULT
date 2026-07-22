import { cn } from "../cn";

/** The 1px graphite hairline that separates every section — the page's structural line work. */
export function Divider({ className }: { className?: string }) {
  return <hr className={cn("saga-divider", className)} />;
}
