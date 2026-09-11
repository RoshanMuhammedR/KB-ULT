import { Fragment, type ReactNode } from "react";

/**
 * Copy in `content.ts` carries three inline marks and nothing else: `<em>` (a dimmed word in
 * a statement), `<span>` (a highlighted one) and `<br/>` (a deliberate line break in display
 * type). Parsing them here keeps the copy readable as copy, and keeps markup out of
 * `dangerouslySetInnerHTML`.
 */
const MARK = /<br\s*\/?>|<em>(.*?)<\/em>|<span>(.*?)<\/span>/gi;

export function rich(text: string): ReactNode {
  if (!text.includes("<")) return text;
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(MARK)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(text.slice(last, index));
    if (match[0].toLowerCase().startsWith("<br")) nodes.push(<br key={key++} />);
    else if (match[1] !== undefined) nodes.push(<em key={key++}>{match[1]}</em>);
    else nodes.push(<span key={key++}>{match[2]}</span>);
    last = index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <Fragment>{nodes}</Fragment>;
}

/** The same copy with its marks removed, for `aria-label`s and metadata. */
export function plain(text: string): string {
  return text.replace(/<br\s*\/?>/gi, " ").replace(/<\/?(em|span)>/gi, "").replace(/\s+/g, " ").trim();
}
