import { cn } from "../cn";

type Props = {
  /** Optional href turns the wordmark into a link (apps wrap with their router's Link instead). */
  className?: string;
  /** Show the small gold compass mark before the wordmark. */
  mark?: boolean;
};

/**
 * Saga wordmark. Weight 400, tight tracking — authority through scale, not boldness. The mark is
 * a single Compass Gold dot: the system's one warm accent, used only as punctuation.
 */
export function Logo({ className, mark = true }: Props) {
  return (
    <span className={cn("saga-logo", className)} aria-label="Saga">
      {mark && <span aria-hidden className="saga-logo__mark" />}
      <span className="saga-logo__word">Saga</span>
    </span>
  );
}
