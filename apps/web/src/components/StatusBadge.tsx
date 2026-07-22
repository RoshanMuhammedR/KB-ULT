import { StatusDot, type StatusTone } from "@kb/ui";
import { stageLabel } from "@/lib/progress";

// Status must never rely on color alone — each badge carries a dot AND a text label.
export function StatusBadge({ status }: { status: string }) {
  const tone: StatusTone =
    status === "ready" ? "live" : status === "failed" ? "error" : "warn";
  const processing = status !== "ready" && status !== "failed";
  return (
    <span className="saga-pill">
      <StatusDot tone={tone} pulse={processing} />
      {stageLabel(status)}
    </span>
  );
}
