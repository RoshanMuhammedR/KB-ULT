import { cn } from "@kb/ui";

export function ProgressBar({
  pct,
  active,
  failed
}: {
  pct: number;
  active?: boolean;
  failed?: boolean;
}) {
  return (
    <div
      className={cn("progress", active && "progress--active", failed && "progress--failed")}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="progress__bar" style={{ width: `${Math.max(4, Math.min(100, pct))}%` }} />
    </div>
  );
}
