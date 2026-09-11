"use client";

import { useEffect, useRef, useState } from "react";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/gsap";
import { LOADER } from "@/lib/content";
import { tokenRgb } from "@/lib/color";
import { usePageState } from "@/components/providers/page-state";
import { MARK_CENTER, PETALS } from "@/components/ui/saga-mark";
import { Noise } from "./noise";

// A short, irregular flicker: [blur, spread, alpha] per step, and how long each holds.
const FLICKER: [number, number, number, number][] = [
  [35, 10, 0.85, 0.03],
  [9, 0, 0.5, 0.02],
  [42, 15, 0.8, 0.04],
  [8, 1, 0.6, 0.02],
  [38, 12, 0.85, 0.03],
  [10, 2, 0.7, 0.02],
  [45, 18, 0.8, 0.04],
  [9, 0, 0.5, 0.05]
];

/**
 * The first three seconds of a visit: the labels scramble into place, the corner pins
 * flicker, the spark fills from the bottom, then its four points fold into the centre and
 * the page is handed over.
 */
export function Loader() {
  const ref = useRef<HTMLDivElement>(null);
  const { reveal } = usePageState();
  const [ready, setReady] = useState(false);
  const [done, setDone] = useState(false);

  // A beat on the empty screen before anything moves, as the fonts settle.
  useEffect(() => {
    const timer = setTimeout(() => setReady(true), 1000);
    return () => clearTimeout(timer);
  }, []);

  useGSAP(
    () => {
      const root = ref.current;
      if (!ready || !root) return;

      if (prefersReducedMotion()) {
        gsap
          .timeline({ onComplete: () => setDone(true) })
          .to(root, { autoAlpha: 0, duration: 0.6 })
          .call(reveal, [], 0.1);
        return;
      }

      const dots = root.querySelectorAll(".js-loader-dot");
      const labels = root.querySelectorAll<HTMLElement>(".js-loader-label");
      const fill = root.querySelector(".js-loader-fill");
      const [r, g, b] = tokenRgb("--signal", root, [233, 104, 63]);
      const flicker = FLICKER.map(([blur, spread, alpha, duration]) => ({
        boxShadow: `0 0 ${blur}px ${spread}px rgba(${r}, ${g}, ${b}, ${alpha})`,
        duration
      }));
      const timeline = gsap.timeline({ onComplete: () => setDone(true) });

      labels.forEach((label) => {
        const text = label.textContent ?? "";
        timeline.to(
          label,
          { duration: 1.5, ease: "sine.in", scrambleText: { text, speed: 1, chars: text.replace(/\s/g, "") } },
          0
        );
      });
      timeline
        .to(dots, { keyframes: flicker, ease: "none", stagger: { each: 0.1, from: "random" } }, 0.4)
        .fromTo(fill, { yPercent: 100 }, { yPercent: 0, duration: 1.2, ease: "power2.inOut" }, 0.4)
        .to([...dots, ...labels], { scale: 0, duration: 0.6, ease: "power4.inOut" }, 1.5)
        .addLabel("fold", "-=0.6");

      for (const petal of PETALS) {
        timeline.to(
          root.querySelectorAll(`.js-loader-petal-${petal.key}`),
          {
            scale: 0,
            rotation: "+=180",
            x: MARK_CENTER[0] - petal.center[0],
            y: MARK_CENTER[1] - petal.center[1],
            svgOrigin: `${petal.center[0]} ${petal.center[1]}`,
            duration: 0.8,
            ease: "power4.in"
          },
          "fold"
        );
      }

      timeline
        .addLabel("hide", "fold+=0.4")
        .to(root, { autoAlpha: 0, duration: 1.5, ease: "power2.inOut" }, "hide")
        .call(reveal, [], "hide+=0.2");
    },
    { scope: ref, dependencies: [ready] }
  );

  if (done) return null;

  return (
    <div ref={ref} className="loader" aria-hidden="true">
      <div className="loader__bg" />
      <Noise />
      <p className="loader__label loader__label--top js-loader-label">{LOADER.top}</p>
      <p className="loader__label loader__label--bottom js-loader-label">{LOADER.bottom}</p>
      <div className="loader__dot loader__dot--tl js-loader-dot" />
      <div className="loader__dot loader__dot--tr js-loader-dot" />
      <div className="loader__dot loader__dot--bl js-loader-dot" />
      <div className="loader__dot loader__dot--br js-loader-dot" />
      <div className="loader__wrapper">
        <div className="loader__logo">
          <svg viewBox="1.5 2 21 21">
            <defs>
              <mask id="loader-mark" maskUnits="userSpaceOnUse" x="1.5" y="2" width="21" height="21">
                {PETALS.map((petal) => (
                  <path
                    key={petal.key}
                    d={petal.d}
                    fill="#fff"
                    stroke="#fff"
                    strokeWidth={0.12}
                    className={`js-loader-petal-${petal.key}`}
                  />
                ))}
              </mask>
            </defs>
            <g mask="url(#loader-mark)">
              <rect className="js-loader-fill" x="1.5" y="2" width="21" height="21" fill="var(--ink)" />
            </g>
            <g fill="none" stroke="var(--ink)" strokeWidth="1" strokeLinejoin="round">
              {PETALS.map((petal) => (
                <path
                  key={petal.key}
                  d={petal.edge}
                  vectorEffect="non-scaling-stroke"
                  className={`js-loader-petal-${petal.key}`}
                />
              ))}
            </g>
          </svg>
        </div>
      </div>
    </div>
  );
}
