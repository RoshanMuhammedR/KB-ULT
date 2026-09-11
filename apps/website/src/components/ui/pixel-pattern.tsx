/**
 * A screen of large square pixels, all hidden. A section's exit timeline lights them in a
 * random order until they cover it - in the colour of whatever comes next, which is why the
 * pattern names the surface it is made of - and then the section drops away underneath.
 * That is the whole transition: no wipe, no fade.
 */
const COLS = 17;
const ROWS = 9;
const STEP_X = 67.29;
const STEP_Y = 67.22;
// A touch larger than the step, so neighbouring pixels overlap instead of leaving hairlines.
const SIZE = 68.3;
const WIDTH = STEP_X * (COLS - 1) + SIZE;
const HEIGHT = STEP_Y * (ROWS - 1) + SIZE;

const CELLS = Array.from({ length: COLS * ROWS }, (_, i) => ({
  x: (i % COLS) * STEP_X,
  y: Math.floor(i / COLS) * STEP_Y
}));

export function PixelPattern({ surface }: { surface: "light" | "dark" }) {
  return (
    <div className={`pixel-pattern ${surface}`} aria-hidden="true">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none">
        {CELLS.map((cell, i) => (
          <rect
            key={i}
            className="js-pixel-rect"
            x={cell.x}
            y={cell.y}
            width={SIZE}
            height={SIZE}
            fill="currentColor"
            opacity={0}
          />
        ))}
      </svg>
    </div>
  );
}
