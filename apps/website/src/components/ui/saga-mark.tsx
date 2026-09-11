/**
 * The Saga spark, cut into its four points.
 *
 * Each petal runs from the centre out to one point, bounded by the diagonals through the
 * middle of the curved sides, so the four tile the whole spark and can each be scaled,
 * turned and collapsed on their own.
 */
// `edge` is the petal's outer contour alone: outlining whole petals would draw the diagonals
// they share across the middle of the spark.
const petal = (key: string, edge: string, center: [number, number]) => ({
  key,
  edge,
  d: `M12 12.5L${edge.slice(1)}Z`,
  center
});

export const PETALS = [
  petal("top", "M9.12 9.62A4 4 0 0 0 10.1 8L12 2.5L13.9 8A4 4 0 0 0 14.88 9.62", [12, 7.5]),
  petal("right", "M14.88 9.62A4 4 0 0 0 16.5 10.6L22 12.5L16.5 14.4A4 4 0 0 0 14.88 15.38", [17, 12.5]),
  petal("bottom", "M14.88 15.38A4 4 0 0 0 13.9 17L12 22.5L10.1 17A4 4 0 0 0 9.12 15.38", [12, 17.5]),
  petal("left", "M9.12 15.38A4 4 0 0 0 7.5 14.4L2 12.5L7.5 10.6A4 4 0 0 0 9.12 9.62", [7, 12.5])
];

export const MARK_CENTER = [12, 12.5] as const;

export function SagaMark({ className }: { className?: string }) {
  return (
    <svg viewBox="2 2.5 20 20" className={className} fill="currentColor" aria-hidden="true">
      {PETALS.map((petal) => (
        // The hairline stroke closes the anti-aliasing seam where two petals meet.
        <path
          key={petal.key}
          d={petal.d}
          className="js-petal"
          stroke="currentColor"
          strokeWidth={0.14}
          strokeLinejoin="round"
        />
      ))}
    </svg>
  );
}
