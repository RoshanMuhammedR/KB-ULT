import { FileText, Youtube } from "lucide-react";
import type { Citation, Locator } from "@/types/api";

// Render a citation's source-neutral locator per source. PDF → "page N";
// YouTube → "at m:ss"; anything else falls back to a generic "type value" label.
export function formatLocator(locator: Locator | null): string {
  if (!locator || locator.value === null || locator.value === undefined) return "";
  if (locator.type === "page") return `page ${locator.value}`;
  if (locator.type === "timestamp") {
    const total = Number(locator.value);
    if (Number.isNaN(total)) return "";
    const mins = Math.floor(total / 60);
    const secs = Math.floor(total % 60);
    return `at ${mins}:${secs.toString().padStart(2, "0")}`;
  }
  return `${locator.type} ${locator.value}`;
}

export function CitationCard({ citation }: { citation: Citation }) {
  const loc = formatLocator(citation.locator);
  const isVideo = citation.source_type === "youtube";
  return (
    <div className="citation">
      <div className="citation__head">
        {isVideo ? <Youtube size={14} strokeWidth={1.5} /> : <FileText size={14} strokeWidth={1.5} />}
        {citation.filename}
        {loc ? <span className="citation__loc">· {loc}</span> : null}
        <span className="citation__score">{(citation.score * 100).toFixed(0)}% match</span>
      </div>
      <div className="citation__ex">{citation.excerpt}</div>
    </div>
  );
}
