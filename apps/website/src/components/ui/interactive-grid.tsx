"use client";

import { useRef, useState } from "react";
import { gsap, useGSAP } from "@/lib/gsap";

/**
 * A field of square cells with 1px gutters over a soft accent glow that trails the pointer.
 * The cells hide the glow everywhere except in the gutters, so near the pointer the grid
 * itself seems to light up. Rows alternate alignment, which staggers the columns. The cells
 * are the colour of the surface they sit on, light or dark.
 */
export function InteractiveGrid() {
  const rootRef = useRef<HTMLDivElement>(null);
  const pointRef = useRef<HTMLDivElement>(null);
  const [{ rows, cols }, setSize] = useState({ rows: 5, cols: 9 });

  useGSAP(
    () => {
      const root = rootRef.current;
      const point = pointRef.current;
      const host = root?.parentElement;
      if (!root || !point || !host) return;

      const toX = gsap.quickTo(point, "x", { duration: 0.3, ease: "power3" });
      const toY = gsap.quickTo(point, "y", { duration: 0.3, ease: "power3" });
      const toOpacity = gsap.quickTo(point, "opacity", { duration: 0.4, ease: "bounce" });
      let idle: ReturnType<typeof setTimeout> | undefined;

      const move = (event: PointerEvent) => {
        const box = root.getBoundingClientRect();
        const spot = point.getBoundingClientRect();
        toX(event.clientX - box.left - spot.width / 2);
        toY(event.clientY - box.top - spot.height / 2);
        toOpacity(1);
        clearTimeout(idle);
        idle = setTimeout(() => toOpacity(0), 750);
      };

      const resize = new ResizeObserver(() => {
        const cell = window.innerWidth < 768 ? 150 : 255;
        setSize({
          rows: Math.round(root.clientHeight / cell) + 2,
          cols: Math.round(root.clientWidth / cell) + 2
        });
      });

      host.addEventListener("pointermove", move);
      resize.observe(host);
      return () => {
        host.removeEventListener("pointermove", move);
        resize.disconnect();
        clearTimeout(idle);
      };
    },
    { scope: rootRef }
  );

  return (
    <div ref={rootRef} className="interactive-grid" aria-hidden="true">
      <div className="interactive-grid__container">
        {Array.from({ length: rows }, (_, row) => (
          <div key={row} className="interactive-grid__row">
            {Array.from({ length: cols }, (_, col) => (
              <div key={col} className="interactive-grid__cell" />
            ))}
          </div>
        ))}
        <div ref={pointRef} className="interactive-grid__point" />
      </div>
    </div>
  );
}
