"use client";

import { useRef } from "react";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/gsap";
import { PRIVACY, type PrivacyItem } from "@/lib/content";
import { pixelCells } from "@/components/ui/pixel-icon";

// The display is a square matrix of pixels; each mark is drawn centred on it.
const SIZE = 15;
const INSET = 0.1;
const CELL = 1 - INSET * 2;
const TOTAL = String(PRIVACY.items.length).padStart(2, "0");

const MATRIX = Array.from({ length: SIZE * SIZE }, (_, i) => [i % SIZE, Math.floor(i / SIZE)] as const);
const MARKS = PRIVACY.items.map((item) => {
  const { cells, width, height } = pixelCells(item.icon);
  const dx = Math.floor((SIZE - width) / 2);
  const dy = Math.floor((SIZE - height) / 2);
  return new Set(cells.map(([x, y]) => (y + dy) * SIZE + x + dx));
});

const readouts = (item: PrivacyItem) => [`Saga://vault/${item.icon}`, `${item.index} / ${TOTAL}`, item.status];

/**
 * The privacy section's display: a small dark screen that redraws the current guarantee's
 * mark a pixel at a time, under a scan that runs down it as the section is scrolled through.
 * The section sets `--scan` on it and `--fill` on each progress segment.
 */
export function PrivacyScreen({ active }: { active: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const shown = useRef<number | null>(null);

  useGSAP(
    () => {
      const root = ref.current;
      if (!root) return;
      const cells = root.querySelectorAll<SVGRectElement>(".js-screen-cell");
      const texts = root.querySelectorAll<HTMLElement>(".js-screen-text");
      const mark = MARKS[active];
      // The first mark is simply there; the screen's power-on reveals it.
      const instant = shown.current === null || prefersReducedMotion();
      shown.current = active;

      cells.forEach((cell, i) => {
        const on = mark.has(i);
        if (instant) {
          gsap.set(cell, { opacity: on ? 1 : 0 });
          return;
        }
        if (Number(gsap.getProperty(cell, "opacity")) === (on ? 1 : 0)) return;
        const delay = Math.random() * 0.45;
        if (on) {
          gsap.to(cell, {
            keyframes: [
              { opacity: 1, duration: 0.04 },
              { opacity: 0.25, duration: 0.05 },
              { opacity: 1, duration: 0.06 }
            ],
            delay,
            ease: "none",
            overwrite: true
          });
        } else {
          gsap.to(cell, { opacity: 0, duration: 0.06, delay: delay * 0.6, ease: "none", overwrite: true });
        }
      });

      const values = readouts(PRIVACY.items[active]);
      texts.forEach((element, i) => {
        if (instant) element.textContent = values[i];
        else gsap.to(element, { duration: 0.6, ease: "none", overwrite: true, scrambleText: { text: values[i], chars: "01", speed: 0.8 } });
      });
    },
    { scope: ref, dependencies: [active] }
  );

  // The readouts are written only by the effect above, so React never holds a text node the
  // scramble has replaced; these are their first values.
  const [path, counter, status] = readouts(PRIVACY.items[0]);

  return (
    <div ref={ref} className="privacy-screen dark js-privacy-screen" aria-hidden="true">
      <span className="privacy-screen__pin" />
      <span className="privacy-screen__pin" />
      <span className="privacy-screen__pin" />
      <span className="privacy-screen__pin" />
      <div className="privacy-screen__inner js-privacy-screen-inner">
        <div className="privacy-screen__bar">
          <p className="privacy-screen__live">
            <span className="js-screen-text">{path}</span>
          </p>
          <span className="js-screen-text">{counter}</span>
        </div>
        <div className="privacy-screen__stage">
          <svg className="privacy-screen__matrix" viewBox={`0 0 ${SIZE} ${SIZE}`}>
            <g className="privacy-screen__off">
              {MATRIX.map(([x, y]) => (
                <rect key={`${x}-${y}`} x={x + INSET} y={y + INSET} width={CELL} height={CELL} />
              ))}
            </g>
            <g className="privacy-screen__on">
              {MATRIX.map(([x, y]) => (
                <rect key={`${x}-${y}`} className="js-screen-cell" x={x + INSET} y={y + INSET} width={CELL} height={CELL} />
              ))}
            </g>
          </svg>
          <span className="privacy-screen__beam" />
        </div>
        <div className="privacy-screen__foot">
          <div className="privacy-screen__segments">
            {PRIVACY.items.map((item) => (
              <span key={item.index} className="privacy-screen__segment js-privacy-segment">
                <span />
              </span>
            ))}
          </div>
          <span className="privacy-screen__status js-screen-text">{status}</span>
        </div>
        <span className="privacy-screen__scanlines" />
        <span className="privacy-screen__vignette" />
      </div>
    </div>
  );
}
