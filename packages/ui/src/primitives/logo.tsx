import { cn } from "../cn";

/**
 * The brand mark: a gradient tile with a spark, then the word.
 *
 * `withWordmark={false}` leaves the tile alone, for places that are already labelled — a
 * collapsed rail, a favicon-sized slot, the top of a modal that says "Saga" in its heading.
 */
export function Logo({
  className,
  withWordmark = true
}: {
  className?: string;
  withWordmark?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)} aria-label="Saga">
      <span
        aria-hidden
        className="flex size-8 shrink-0 items-center justify-center rounded-lg text-white shadow-sm"
        // A token-derived gradient rather than two more colour tokens: the lighter stop only
        // ever appears here, and mixing it keeps it correct in both themes for free.
        style={{
          backgroundImage:
            "linear-gradient(to top right, var(--color-primary), color-mix(in oklab, var(--color-primary) 68%, white))"
        }}
      >
        <svg viewBox="0 0 24 24" className="size-4" fill="currentColor">
          <path d="M12 2.5 13.9 8a4 4 0 0 0 2.6 2.6l5.5 1.9-5.5 1.9a4 4 0 0 0-2.6 2.6L12 22.5 10.1 17a4 4 0 0 0-2.6-2.6L2 12.5l5.5-1.9A4 4 0 0 0 10.1 8L12 2.5Z" />
        </svg>
      </span>
      {withWordmark ? (
        <span className="text-[17px] font-semibold tracking-[-0.02em]">Saga</span>
      ) : null}
    </span>
  );
}
