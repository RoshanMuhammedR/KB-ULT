"use client";

import { useId, useRef } from "react";
import { fontsReady, gsap, SplitText, useGSAP } from "@/lib/gsap";
import { CALL, SECTION } from "@/lib/content";
import { rich } from "@/lib/rich";
import { Button } from "@/components/ui/button";

const RINGS = [595, 666, 732];
const CENTRE = 736.5;

/**
 * The last word before the footer. Held for a stretch of scroll while three rings open out
 * from below the headline and the way in rises into place.
 */
export function GetStarted() {
  const ref = useRef<HTMLElement>(null);
  const gradient = useId().replace(/:/g, "");

  useGSAP(
    () => {
      const section = ref.current;
      const title = section?.querySelector<HTMLElement>(".js-title");
      const text = section?.querySelector<HTMLElement>(".js-text");
      const cta = section?.querySelector<HTMLElement>(".js-cta-inner");
      if (!section || !title || !text || !cta) return;
      const rings = section.querySelectorAll(".js-ring");

      const media = gsap.matchMedia();
      media.add({ touchless: "(pointer: none)", pointer: "(pointer: fine), (pointer: coarse)" }, (context) => {
        const { touchless } = context.conditions as { touchless: boolean };
        const timeline = gsap
          .timeline({
            scrollTrigger: {
              trigger: section,
              start: "top top",
              end: touchless ? "+=3000" : "+=1500",
              pin: true,
              scrub: true,
              id: SECTION.getStarted,
              invalidateOnRefresh: true
            }
          })
          .fromTo(
            rings,
            { scale: 0, y: 120, transformOrigin: "50% 50%" },
            { scale: 1.8, y: 0, duration: 3.2, stagger: { each: 0.1, from: "end" } },
            0
          )
          .from(rings, { opacity: 0, duration: 0.8, stagger: { each: 0.1, from: "end" } }, 0.1)
          .from(cta, { yPercent: 110, duration: 0.8, ease: "power4.inOut" }, 0.8);

        // Cut into words and lines once the webfont is in; see `fontsReady`.
        const splitCopy = () => {
          let titleTimeline: gsap.core.Timeline | null = null;
          SplitText.create(title, {
            type: "words,chars",
            wordsClass: "word",
            charsClass: "char",
            autoSplit: true,
            onRevert() {
              if (!titleTimeline) return;
              timeline.remove(titleTimeline);
              titleTimeline.revert();
              titleTimeline = null;
            },
            onSplit(self) {
              titleTimeline = gsap
                .timeline()
                .from(self.chars, { opacity: 0, duration: 0.3, stagger: 0.05, ease: "power4.inOut" }, 0)
                .from(title, { yPercent: 120, duration: 1, ease: "power1" }, 0);
              timeline.add(titleTimeline, 0);
            }
          });

          let textTimeline: gsap.core.Timeline | null = null;
          SplitText.create(text, {
            type: "lines,words,chars",
            linesClass: "line",
            wordsClass: "word",
            charsClass: "char",
            autoSplit: true,
            onRevert() {
              if (!textTimeline) return;
              timeline.remove(textTimeline);
              textTimeline.revert();
              textTimeline = null;
            },
            onSplit(self) {
              const lines = gsap.timeline();
              self.lines.forEach((line, i) => {
                lines
                  .from(line.querySelectorAll(".char"), { opacity: 0, duration: 0.2, stagger: 0.005, ease: "power4.inOut" }, 0.15 * i)
                  .from(line, { y: 30, duration: 0.8, ease: "power4" }, 0.15 * i);
              });
              textTimeline = lines;
              timeline.add(lines, 0.8);
            }
          });
        };

        let live = true;
        fontsReady().then(() => {
          if (live) context.add(splitCopy);
        });
        return () => {
          live = false;
        };
      });

      return () => media.revert();
    },
    { scope: ref }
  );

  return (
    <section ref={ref} id={SECTION.getStarted} className="call-section js-section-spy">
      <div className="call-section__pattern" aria-hidden="true">
        <svg viewBox="0 0 1473 1473" fill="none" preserveAspectRatio="none">
          <defs>
            {RINGS.map((radius, i) => (
              <linearGradient
                key={radius}
                id={`${gradient}-${i}`}
                x1={CENTRE}
                y1={CENTRE - radius}
                x2={CENTRE}
                y2={CENTRE + radius}
                gradientUnits="userSpaceOnUse"
              >
                <stop offset="0.1" style={{ stopColor: "var(--surface-raised)" }} />
                <stop offset="0.37" style={{ stopColor: "var(--signal)" }} />
                <stop offset="0.57" style={{ stopColor: "var(--signal)" }} />
                <stop offset="0.9" style={{ stopColor: "var(--surface-raised)" }} />
              </linearGradient>
            ))}
          </defs>
          {RINGS.map((radius, i) => (
            <circle
              key={radius}
              className="js-ring"
              cx={CENTRE}
              cy={CENTRE}
              r={radius}
              stroke={`url(#${gradient}-${i})`}
              strokeWidth={1.15 + i * 0.06}
            />
          ))}
        </svg>
      </div>
      <div className="call-section__content">
        <h2 className="t-2xl call-section__title js-title">{rich(CALL.title)}</h2>
        <p className="t-md call-section__text js-text">{CALL.text}</p>
        <div className="call-section__cta">
          <div className="js-cta-inner">
            <Button label={CALL.cta.label} href={CALL.cta.href} />
          </div>
        </div>
      </div>
    </section>
  );
}
