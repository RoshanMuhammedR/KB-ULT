"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Paperclip } from "lucide-react";
import { formatLocator } from "@kb/shared";
import { Panel, Pill, SourceIcon } from "@kb/ui";
import { DEMO_ANSWER, DEMO_CITATIONS, DEMO_QUESTION } from "@/lib/demo-content";

/** Shows the product rather than describing it: the answer streams, then its citations land. */
export function AnswerDemo() {
  const [chars, setChars] = useState(0);
  const done = chars >= DEMO_ANSWER.length;

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setChars(DEMO_ANSWER.length);
      return;
    }
    const id = window.setInterval(() => {
      setChars((current) => {
        if (current >= DEMO_ANSWER.length) {
          window.clearInterval(id);
          return current;
        }
        return current + 3;
      });
    }, 16);
    return () => window.clearInterval(id);
  }, []);

  const shown = DEMO_ANSWER.slice(0, chars);
  const paragraphs = shown.split("\n\n");

  return (
    <Panel className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <span className="label-caps text-muted-foreground">Conversation</span>
        <span className="font-mono text-[12px] text-muted-soft">grounded in 5 sources</span>
      </div>

      <div className="space-y-5 p-5">
        <p className="text-[15px] font-semibold">{DEMO_QUESTION}</p>

        <div aria-live="polite" className="text-[15px] leading-relaxed text-foreground">
          {paragraphs.map((paragraph, index) => (
            <p key={index} className={index ? "mt-3" : ""}>
              {paragraph}
              {!done && index === paragraphs.length - 1 ? (
                <span className="stream-caret text-primary">▌</span>
              ) : null}
            </p>
          ))}
        </div>

        {/* Mirrors the product's SourcesChip: collapsed by default, expandable. Shown here
            already open so a visitor sees what is behind it without having to click. */}
        {done ? (
          <div className="border-t border-border pt-4">
            <span
              className={
                "inline-flex items-center gap-1.5 rounded-full border border-border bg-card " +
                "px-2.5 py-1 text-[12px] text-muted-foreground"
              }
            >
              <Paperclip className="size-3.5" aria-hidden />
              {DEMO_CITATIONS.length} sources
              <ChevronDown className="size-3.5 rotate-180" aria-hidden />
            </span>
            <div className="mt-1.5 rounded-md border border-border-soft bg-canvas-soft p-1">
              {DEMO_CITATIONS.map((citation) => (
                <div key={citation.chunk_index} className="p-1">
                  <div className="flex items-center gap-2 px-1.5 pb-1">
                    <SourceIcon type={citation.source_type} className="size-5" />
                    <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">
                      {citation.filename}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 rounded-md px-1.5 py-1.5">
                    <Pill>{formatLocator(citation.locator)}</Pill>
                    <span className="ml-auto shrink-0 text-[12px] text-muted-foreground">
                      {Math.round(citation.score * 100)}%
                    </span>
                    <ChevronRight className="size-3.5 shrink-0 text-muted-soft" aria-hidden />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
