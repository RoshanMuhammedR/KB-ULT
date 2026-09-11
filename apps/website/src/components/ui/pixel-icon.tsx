/**
 * Icons drawn on a pixel grid, one `#` per lit cell. Cells are inset so neighbours never
 * merge - the gaps are what make them read as pixels rather than as a bitmap.
 */
const ICONS = {
  arrow: ["...#...", "....#..", ".....#.", "#######", ".....#.", "....#..", "...#..."],
  arrowDown: ["...#...", "...#...", "...#...", "#..#..#", ".#.#.#.", "..###..", "...#..."],
  chevrons: ["#....#.....", ".#....#....", "..#....#...", ".#....#....", "#....#....."],
  arrowLarge: [
    "....#....",
    ".....#...",
    "......#..",
    ".......#.",
    "#########",
    ".......#.",
    "......#..",
    ".....#...",
    "....#...."
  ],
  rows: [
    "###########",
    "#...#.....#",
    "###########",
    "#...#.....#",
    "###########",
    "#...#.....#",
    "###########"
  ],
  lock: [
    "...#####...",
    "..#.....#..",
    "..#.....#..",
    "..#.....#..",
    "###########",
    "#.........#",
    "#....#....#",
    "#....#....#",
    "#.........#",
    "###########"
  ],
  erase: [
    "....###....",
    "###########",
    ".#.......#.",
    ".#.#.#.#.#.",
    ".#.#.#.#.#.",
    ".#.#.#.#.#.",
    ".#.#.#.#.#.",
    ".#.......#.",
    "..#######.."
  ],
  model: [
    "...#####...",
    ".##.....##.",
    ".#......##.",
    "#......#..#",
    "#.....#...#",
    "#....#....#",
    "#...#.....#",
    "#..#......#",
    ".##......#.",
    ".##.....##.",
    "...#####..."
  ]
} as const;

export type PixelIconName = keyof typeof ICONS;

const INSET = 0.07;
const CELL = 1 - INSET * 2;

function toPath(rows: readonly string[]) {
  let d = "";
  rows.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      if (row[x] === "#") d += `M${x + INSET} ${y + INSET}h${CELL}v${CELL}h-${CELL}z`;
    }
  });
  return d;
}

const PATHS = Object.fromEntries(
  Object.entries(ICONS).map(([name, rows]) => [name, { d: toPath(rows), w: rows[0].length, h: rows.length }])
) as Record<PixelIconName, { d: string; w: number; h: number }>;

export function PixelIcon({ name, className }: { name: PixelIconName; className?: string }) {
  const { d, w, h } = PATHS[name];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={className} fill="currentColor" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}
