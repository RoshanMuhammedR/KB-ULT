import { cn } from "../cn";

export type StatusTone = "neutral" | "live" | "warn" | "error";

const TONE_CLASS: Record<StatusTone, string> = {
  neutral: "",
  live: "saga-dot--live",
  warn: "saga-dot--warn",
  error: "saga-dot--error"
};

/** A 6px status dot. Never the sole signal — always pair with a text label for accessibility. */
export function StatusDot({
  tone = "neutral",
  pulse = false,
  className
}: {
  tone?: StatusTone;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn("saga-dot", TONE_CLASS[tone], pulse && "saga-dot--pulse", className)}
    />
  );
}
