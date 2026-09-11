"use client";

import { useId, useRef } from "react";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/gsap";
import { RETRIEVAL } from "@/lib/content";
import type { Step } from "@/lib/content";

/**
 * The small looping illustrations at the top of each step card: grey hairlines for
 * structure, the accent (with its glow) for whatever is happening.
 */
export function StepMedia({ kind }: { kind: Step["media"] }) {
  if (kind === "add") return <AddMedia />;
  if (kind === "ask") return <AskMedia />;
  return <CiteMedia />;
}

const W = 560;
const H = 281;
const LINE = "color-mix(in oklab, var(--ink) 26%, transparent)";
const FAINT = "color-mix(in oklab, var(--ink) 12%, transparent)";
const ACCENT = "var(--signal)";

function Glow({ id }: { id: string }) {
  return (
    <filter id={id} x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="3" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
  );
}

function hexagon(cx: number, cy: number, r: number) {
  return Array.from({ length: 6 }, (_, i) => {
    const a = ((-90 + i * 60) * Math.PI) / 180;
    return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
  }).join(" ");
}

/** [001] Sources flow from a document into the library, through an orbit of passages. */
function AddMedia() {
  const glow = useId().replace(/:/g, "");
  const orbitA = "M234 140a46 16 0 1 0 92 0a46 16 0 1 0 -92 0";
  return (
    <svg className="service-card__media" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      <defs>
        <Glow id={glow} />
      </defs>
      <polygon points={hexagon(120, 140, 50)} fill="none" stroke={LINE} />
      <g fill="none" stroke={LINE} strokeLinejoin="round">
        <path d="M106 116h20l10 10v36h-30z" />
        <path d="M126 116v10h10" />
        <path d="M112 136h18M112 144h18M112 152h12" />
      </g>
      <polygon points={hexagon(440, 140, 50)} fill="none" stroke={LINE} />
      <g fill="none" stroke={LINE}>
        <rect x="420" y="120" width="40" height="9" rx="2" />
        <rect x="420" y="135.5" width="40" height="9" rx="2" />
        <rect x="420" y="151" width="40" height="9" rx="2" />
      </g>
      <path d="M170 140H390" stroke={FAINT} strokeDasharray="2 4" />
      <g filter={`url(#${glow})`} fill={ACCENT}>
        {[0, 1, 2].map((i) => (
          <rect key={i} y="137" width="6" height="6">
            <animate attributeName="x" from="170" to="384" dur="2.4s" begin={`${i * 0.8}s`} repeatCount="indefinite" />
            <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.15;0.85;1" dur="2.4s" begin={`${i * 0.8}s`} repeatCount="indefinite" />
          </rect>
        ))}
      </g>
      <g transform="rotate(-24 280 140)">
        <path d={orbitA} fill="none" stroke={LINE} />
        <circle r="3.5" fill={ACCENT} filter={`url(#${glow})`}>
          <animateMotion dur="3.2s" repeatCount="indefinite" path={orbitA} />
        </circle>
      </g>
      <g transform="rotate(24 280 140)">
        <path d={orbitA} fill="none" stroke={LINE} />
        <circle r="3.5" fill={ACCENT} filter={`url(#${glow})`}>
          <animateMotion dur="4.1s" begin="-1.3s" repeatCount="indefinite" path={orbitA} />
        </circle>
      </g>
      <circle cx="280" cy="140" r="4" fill={ACCENT} filter={`url(#${glow})`} />
    </svg>
  );
}

const RING_R = 29;
const RING_C = 2 * Math.PI * RING_R;

/** [002] Retrieval: the demo answer's cited passages, scored, and the count that made the cut. */
function AskMedia() {
  const ref = useRef<SVGSVGElement>(null);
  const glow = useId().replace(/:/g, "");
  const rings = [
    ...RETRIEVAL.map((item) => ({ value: item.score, label: item.label, display: (n: number) => String(n) })),
    { value: 100, label: "Cited", display: (n: number) => String(Math.round((n / 100) * RETRIEVAL.length)).padStart(2, "0") }
  ];

  useGSAP(
    () => {
      const svg = ref.current;
      if (!svg) return;
      const arcs = svg.querySelectorAll<SVGCircleElement>(".js-arc");
      const numbers = svg.querySelectorAll<SVGTextElement>(".js-number");
      const counters = rings.map(() => ({ n: 0 }));
      const paint = (i: number) => {
        numbers[i].textContent = rings[i].display(Math.round(counters[i].n));
        arcs[i].style.strokeDashoffset = String(RING_C * (1 - counters[i].n / 100));
      };
      rings.forEach((_, i) => paint(i));
      if (prefersReducedMotion()) {
        rings.forEach((ring, i) => {
          counters[i].n = ring.value;
          paint(i);
        });
        return;
      }
      const timeline = gsap.timeline({ repeat: -1, repeatDelay: 0.4 });
      rings.forEach((ring, i) => {
        timeline.to(counters[i], { n: ring.value, duration: 1.4, ease: "power2.out", onUpdate: () => paint(i) }, i * 0.18);
      });
      timeline.to(counters, { n: 0, duration: 0.7, ease: "power2.in", onUpdate: () => rings.forEach((_, i) => paint(i)) }, "+=2.2");
    },
    { scope: ref }
  );

  const spacing = 110;
  const first = W / 2 - spacing * 1.5;
  return (
    <svg ref={ref} className="service-card__media" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      <defs>
        <Glow id={glow} />
      </defs>
      <rect
        x="58"
        y="62"
        width="444"
        height="160"
        fill="none"
        stroke="color-mix(in oklab, var(--signal) 45%, transparent)"
        strokeDasharray="3 3"
      />
      {rings.map((ring, i) => {
        const cx = first + i * spacing;
        return (
          <g key={ring.label}>
            <circle cx={cx} cy="130" r={RING_R} fill="none" stroke={FAINT} strokeWidth="3" />
            <circle
              className="js-arc"
              cx={cx}
              cy="130"
              r={RING_R}
              fill="none"
              stroke={ACCENT}
              strokeWidth="3"
              strokeDasharray={RING_C}
              strokeDashoffset={RING_C}
              transform={`rotate(-90 ${cx} 130)`}
              filter={`url(#${glow})`}
            />
            <text
              className="js-number"
              x={cx}
              y="137"
              textAnchor="middle"
              fill="var(--ink)"
              style={{ font: "700 19px var(--font-mono)" }}
            >
              00
            </text>
            <text
              x={cx}
              y="188"
              textAnchor="middle"
              fill={LINE}
              style={{ font: "700 9px var(--font-mono)", letterSpacing: "0.04em", textTransform: "uppercase" }}
            >
              {ring.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** [003] A page of the source, the cited passage marked, and the tag it answers to. */
function CiteMedia() {
  const ref = useRef<SVGSVGElement>(null);
  const glow = useId().replace(/:/g, "");
  const cited = RETRIEVAL[0];
  const lines = [96, 104, 88, 100, 70, 104, 98, 104, 84, 60];

  useGSAP(
    () => {
      const svg = ref.current;
      if (!svg) return;
      const mark = svg.querySelector(".js-mark");
      const link = svg.querySelector<SVGPathElement>(".js-link");
      const tag = svg.querySelector(".js-tag");
      const node = svg.querySelector(".js-node");
      if (!mark || !link || !tag || !node || prefersReducedMotion()) return;
      const length = link.getTotalLength();
      gsap.set(link, { strokeDasharray: length, strokeDashoffset: length });
      gsap
        .timeline({ repeat: -1, repeatDelay: 0.5 })
        .fromTo(mark, { scaleX: 0 }, { scaleX: 1, transformOrigin: "0% 50%", duration: 0.8, ease: "power2.inOut" })
        .fromTo(node, { scale: 0 }, { scale: 1, transformOrigin: "50% 50%", duration: 0.35, ease: "back.out(3)" }, "-=0.1")
        .to(link, { strokeDashoffset: 0, duration: 0.6, ease: "power2.out" }, "<")
        .fromTo(tag, { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.4, ease: "power2.out" }, "-=0.2")
        .to([mark, node, tag], { opacity: 0, duration: 0.5, ease: "power1.in" }, "+=2.2")
        .to(link, { strokeDashoffset: length, duration: 0.5, ease: "power1.in" }, "<")
        .set([mark, node, tag], { opacity: 1 })
        .set(mark, { scaleX: 0 });
    },
    { scope: ref }
  );

  return (
    <svg ref={ref} className="service-card__media" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      <defs>
        <Glow id={glow} />
      </defs>
      <path d="M150 38h118l22 22v183H150z" fill="none" stroke={LINE} strokeLinejoin="round" />
      <path d="M268 38v22h22" fill="none" stroke={LINE} strokeLinejoin="round" />
      {lines.map((width, i) => (
        <rect key={i} x="166" y={74 + i * 15} width={width} height="4" rx="2" fill={FAINT} />
      ))}
      <rect
        className="js-mark"
        x="160"
        y="130"
        width="120"
        height="35"
        fill="color-mix(in oklab, var(--signal) 20%, transparent)"
        stroke={ACCENT}
        strokeWidth="1"
        filter={`url(#${glow})`}
      />
      <path className="js-link" d="M280 147H322L352 112H384" fill="none" stroke={ACCENT} strokeDasharray="3 3" />
      <circle className="js-node" cx="352" cy="112" r="4.5" fill={ACCENT} filter={`url(#${glow})`} />
      <g className="js-tag">
        <rect x="384" y="94" width="112" height="36" fill="none" stroke={ACCENT} strokeDasharray="3 3" />
        <text x="440" y="116" textAnchor="middle" fill="var(--ink)" style={{ font: "700 11px var(--font-mono)", textTransform: "uppercase" }}>
          {cited.label} · {cited.score}%
        </text>
      </g>
    </svg>
  );
}
