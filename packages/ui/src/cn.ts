/** Tiny classnames joiner — filters falsy values so callers can pass conditionals. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
