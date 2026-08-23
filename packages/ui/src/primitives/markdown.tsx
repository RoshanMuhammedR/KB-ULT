"use client";

import Markdown from "markdown-to-jsx";
import { useMemo, type ReactNode } from "react";

import { cn } from "../cn";

/**
 * Renders an assistant answer's markdown.
 *
 * `markdown-to-jsx` rather than a remark/rehype stack: it is about 6kB, it compiles straight
 * to React elements (so there is no `innerHTML` anywhere in the path), and every tag is
 * replaceable through `overrides` — which is what makes the styling below ordinary app code
 * rather than a plugin pipeline. It also tolerates half-finished input, which matters here
 * because this re-renders on every streamed token: mid-answer the source routinely has an
 * unclosed fence or a dangling `**`.
 *
 * **Two deliberate restrictions, both about untrusted content.** An answer is written from
 * retrieved documents, and a document is data from outside the system — the prompt says as
 * much. So a source that talks the model into emitting markup must land as visible text:
 *
 *   * `disableParsingRawHTML` — inline HTML is printed, never mounted.
 *   * `img` is not loaded. A markdown image is an automatic outbound GET the moment an
 *     answer renders, which is an exfiltration channel (`![](https://…/?q=secrets)`) that
 *     needs no click. The alt text and the URL are shown as inert text instead.
 *
 * Ordinal citations (`[1]`, `[2]`) need no special handling: a bracketed number with no
 * matching link definition is literal text in CommonMark, so it renders exactly as written.
 */
export function Prose({
  children,
  streaming = false,
  className
}: {
  children: string;
  /** Attaches the blinking caret to the last rendered block. */
  streaming?: boolean;
  className?: string;
}) {
  // Rebuilt only when the streaming flag flips, not on every token.
  const options = useMemo(
    () => ({
      forceBlock: true,
      // Without this a single-paragraph answer compiles to a bare <p> and `className` lands
      // on that paragraph, colliding with the `p` override below - which is how the caret
      // silently went missing. A guaranteed wrapper makes the shape the CSS targets stable.
      forceWrapper: true,
      // Suppresses inline syntax that has not closed yet, so a half-written `**bold` shows
      // as text rather than flashing its asterisks on every token. Off once the answer is
      // complete, where there is nothing left to wait for.
      optimizeForStreaming: streaming,
      disableParsingRawHTML: true,
      overrides: {
          p: { props: { className: "text-[15px] leading-relaxed" } },
          a: {
            props: {
              className: "text-primary underline underline-offset-2 hover:no-underline",
              target: "_blank",
              // noreferrer as well as noopener: an answer's links point wherever a source
              // document pointed, and those destinations get no referrer from us.
              rel: "noopener noreferrer nofollow"
            }
          },
          ul: { props: { className: "list-disc space-y-1 pl-5 text-[15px] leading-relaxed" } },
          ol: { props: { className: "list-decimal space-y-1 pl-5 text-[15px] leading-relaxed" } },
          li: { props: { className: "pl-1" } },
          h1: { props: { className: "text-lg font-semibold" } },
          h2: { props: { className: "text-base font-semibold" } },
          h3: { props: { className: "text-[15px] font-semibold" } },
          h4: { props: { className: "text-[15px] font-medium" } },
          h5: { props: { className: "text-[15px] font-medium" } },
          h6: { props: { className: "text-[15px] font-medium" } },
          strong: { props: { className: "font-semibold" } },
          hr: { props: { className: "border-border" } },
          blockquote: {
            props: { className: "border-l-2 border-border pl-3 text-muted-foreground italic" }
          },
          code: { component: Code },
          pre: { component: Pre },
          table: { component: Table },
          th: { props: { className: "border border-border px-2 py-1 text-left font-medium" } },
          td: { props: { className: "border border-border px-2 py-1 align-top" } },
          img: { component: InertImage }
        }
      }),
    [streaming]
  );

  return (
    <Markdown
      className={cn("space-y-3", streaming && "prose-streaming", className)}
      options={options}
    >
      {children}
    </Markdown>
  );
}

/** Inline code, and the inner half of a fenced block — `pre` styles the box around it. */
function Code({ className, children, ...rest }: { className?: string; children?: ReactNode }) {
  return (
    <code
      {...rest}
      className={cn(
        "rounded bg-muted px-1 py-0.5 font-mono text-[13px]",
        // Inside a fence the box, padding and background belong to `pre`, not to each line.
        "[pre_&]:bg-transparent [pre_&]:p-0 [pre_&]:text-[13px]",
        className
      )}
    >
      {children}
    </code>
  );
}

/**
 * A fenced block. `overflow-x-auto` on the block itself, so a long line scrolls inside its
 * own box instead of widening the message and putting a horizontal scrollbar on the thread.
 */
function Pre({ children, ...rest }: { children?: ReactNode }) {
  return (
    <pre
      {...rest}
      className="overflow-x-auto rounded-md border border-border bg-muted p-3 font-mono text-[13px] leading-relaxed"
    >
      {children}
    </pre>
  );
}

/** Same reasoning as `Pre`: a wide table scrolls in place rather than stretching the thread. */
function Table({ children, ...rest }: { children?: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table {...rest} className="w-full border-collapse text-[14px]">
        {children}
      </table>
    </div>
  );
}

/**
 * An image reference, shown but never fetched. See the note on `Prose`: rendering a real
 * `<img>` would turn a line of a retrieved document into an automatic outbound request.
 */
function InertImage({ alt, src }: { alt?: string; src?: string }) {
  return (
    <span className="text-[13px] text-muted-foreground italic">
      [image: {alt?.trim() || "untitled"}
      {src ? ` — ${src}` : ""}]
    </span>
  );
}
