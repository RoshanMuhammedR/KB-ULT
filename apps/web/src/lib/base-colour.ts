import { BASE_COLOURS, type BaseColour, type KnowledgeBase } from "@/types/api";

/**
 * Class names per base colour, written out rather than built.
 *
 * Tailwind reads source files as text — `bg-base-${colour}` produces nothing, because there
 * is no such string in the source for it to find. So each combination is spelled out here,
 * once, and every base tile and chip in the app reads from this map.
 */
const TILE: Record<BaseColour, string> = {
  amber: "bg-base-amber",
  rose: "bg-base-rose",
  violet: "bg-base-violet",
  sky: "bg-base-sky",
  emerald: "bg-base-emerald",
  slate: "bg-base-slate"
};

const DOT: Record<BaseColour, string> = TILE;

const TEXT: Record<BaseColour, string> = {
  amber: "text-base-amber",
  rose: "text-base-rose",
  violet: "text-base-violet",
  sky: "text-base-sky",
  emerald: "text-base-emerald",
  slate: "text-base-slate"
};

const RING: Record<BaseColour, string> = {
  amber: "ring-base-amber",
  rose: "ring-base-rose",
  violet: "ring-base-violet",
  sky: "ring-base-sky",
  emerald: "ring-base-emerald",
  slate: "ring-base-slate"
};

/**
 * The colour a base is drawn in.
 *
 * Bases created before colours existed have none, and asking every such user to go and pick
 * one would be a chore for no benefit — so an unset colour is derived from the id instead.
 * Deriving from the id rather than the name means renaming a base does not change its
 * colour, which is the whole point of having one.
 */
export function baseColour(base: Pick<KnowledgeBase, "id" | "colour">): BaseColour {
  const stored = BASE_COLOURS.find((option) => option === base.colour);
  if (stored) return stored;
  let hash = 0;
  for (const char of base.id) hash = (hash * 31 + char.charCodeAt(0)) % 100000;
  return BASE_COLOURS[hash % BASE_COLOURS.length]!;
}

export function baseTileClass(base: Pick<KnowledgeBase, "id" | "colour">): string {
  return TILE[baseColour(base)];
}

export function baseDotClass(base: Pick<KnowledgeBase, "id" | "colour">): string {
  return DOT[baseColour(base)];
}

export function baseTextClass(base: Pick<KnowledgeBase, "id" | "colour">): string {
  return TEXT[baseColour(base)];
}

export function baseRingClass(base: Pick<KnowledgeBase, "id" | "colour">): string {
  return RING[baseColour(base)];
}

export function swatchClass(colour: BaseColour): string {
  return TILE[colour];
}

/** The letter shown on a base tile. Falls back to "?" so an empty name still renders one. */
export function baseInitial(name: string): string {
  return (name.trim()[0] ?? "?").toUpperCase();
}
