"use client";

import { useRef } from "react";
import { fontsReady, gsap, SplitText, useGSAP } from "@/lib/gsap";
import { GROUNDING } from "@/lib/content";
import { Button } from "@/components/ui/button";
import { createGroundingScene, FINAL_SHIFT, initialGroundingState } from "@/components/webgl/grounding-scene";
import { useThreeScene } from "@/components/webgl/use-three-scene";

/**
 * Seven and a half screens of scroll for one idea. The threads drift in with their labels
 * while the statement holds the corner; then they draw together into a single point, the
 * statement falls away, and the headline and the way in take its place.
 */
export function Grounding() {
  const ref = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const labelRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const state = useRef(initialGroundingState()).current;

  useThreeScene(canvasRef, (renderer, container) =>
    createGroundingScene(renderer, container, { lines: GROUNDING.lines, state, labels: labelRefs.current })
  );

  useGSAP(
    () => {
      const section = ref.current;
      if (!section) return;
      const statement = section.querySelector<HTMLElement>(".data-viz-section__title");
      const title = section.querySelector<HTMLElement>(".data-viz-section__center-title");
      const text = section.querySelector<HTMLElement>(".data-viz-section__center-text");
      const button = section.querySelector<HTMLElement>(".data-viz-section__center-button");
      if (!statement || !title || !text || !button) return;

      const media = gsap.matchMedia();
      media.add({ mobile: "(max-width: 767px)", desktop: "(min-width: 768px)" }, (context) => {
        const { mobile } = context.conditions as { mobile: boolean };
        state.mobile = mobile;

        const timeline = gsap.timeline({
          scrollTrigger: { trigger: section, start: "top top", end: "bottom bottom", pin: ".data-viz-section__container", scrub: true },
          defaults: { ease: "none" }
        });
        timeline
          .fromTo(state, { enter: 12 }, { enter: -0.5, duration: 0.6, ease: "power1" }, 0)
          .fromTo(state, { fuse: 0 }, { fuse: 1, enter: -1.5, duration: 0.4, ease: "power1.inOut", immediateRender: false }, 0.6)
          .fromTo(state, { shiftX: 0 }, { shiftX: mobile ? 0 : -FINAL_SHIFT, duration: 0.2, ease: "power1.inOut", immediateRender: false }, 0.9)
          .fromTo(state, { highlight: 0 }, { highlight: 1, duration: 0.08, ease: "power1.inOut", immediateRender: false }, 0.92)
          .fromTo(state, { highlightLabel: 1 }, { highlightLabel: 0, duration: 0.04, ease: "power1.inOut", immediateRender: false }, 0.96);

        // The statement and the headline are cut into words once the webfont is in (see
        // `fontsReady`); their timelines join the scrubbed one at fixed positions, so arriving
        // late costs nothing.
        const splitCopy = () => {
          let statementTimeline: gsap.core.Timeline | null = null;
          SplitText.create(statement, {
            type: "lines,words",
            tag: "span",
            linesClass: "line",
            wordsClass: "word",
            autoSplit: true,
            onRevert() {
              if (!statementTimeline) return;
              timeline.remove(statementTimeline);
              statementTimeline.revert();
              statementTimeline = null;
            },
            onSplit(self) {
              const random = { amount: 0.1, from: "random" as const };
              statementTimeline = gsap
                .timeline({ defaults: { ease: "none" } })
                .from(statement, { yPercent: 100, duration: 0.3, ease: "power4" }, 0)
                .from(self.words, { opacity: 0, duration: 0.2, ease: "bounce.inOut", stagger: random }, 0)
                .to(self.words, { opacity: 0, duration: 0.2, ease: "bounce.inOut", stagger: random }, 0.6)
                .to(statement, { yPercent: 100, duration: 0.4, ease: "power4.in" }, 0.6);
              timeline.add(statementTimeline, 0);
            }
          });

          let centerTimeline: gsap.core.Timeline | null = null;
          SplitText.create([title, text], {
            type: "lines,words,chars",
            tag: "span",
            linesClass: "line",
            wordsClass: "word",
            charsClass: "char",
            autoSplit: true,
            onRevert() {
              if (!centerTimeline) return;
              timeline.remove(centerTimeline);
              centerTimeline.revert();
              centerTimeline = null;
            },
            onSplit(self) {
              const titleChars = self.chars.filter((char) => title.contains(char));
              const textWords = self.words.filter((word) => text.contains(word));
              centerTimeline = gsap
                .timeline({ defaults: { ease: "none" } })
                .from([title, text, button], { x: mobile ? 0 : 50, y: mobile ? 50 : 0, duration: 0.2, ease: "power1.inOut" }, 0.9)
                .from(titleChars, { opacity: 0, duration: 0.1, stagger: 0.008, ease: "power4.inOut" }, 0.9)
                .from(textWords, { opacity: 0, duration: 0.2, ease: "bounce.inOut", stagger: { amount: 0.05, from: "random" } }, 0.9)
                .from(button, { opacity: 0, yPercent: 25, duration: 0.1, ease: "power2.inOut" }, 0.95);
              timeline.add(centerTimeline, 0);
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
    <section ref={ref} className="data-viz-section">
      <div className="data-viz-section__container">
        <div className="data-viz-section__canvas">
          <div ref={canvasRef} className="webgl" aria-hidden="true" />
          <div className="data-viz-section__labels" aria-hidden="true">
            {GROUNDING.lines.map((line, index) => (
              <span
                key={line.label}
                ref={(element) => {
                  labelRefs.current[index] = element;
                }}
                className="data-viz-section__label"
              >
                {line.label}
              </span>
            ))}
          </div>
          <div className="data-viz-section__canvas-veil" />
        </div>
        <div className="data-viz-section__bottom">
          <p className="t-lg data-viz-section__title">{GROUNDING.statement}</p>
        </div>
        <div className="data-viz-section__center">
          <h2 className="t-2lg data-viz-section__center-title">{GROUNDING.title}</h2>
          <p className="t-md data-viz-section__center-text">{GROUNDING.text}</p>
          <Button label={GROUNDING.cta.label} href={GROUNDING.cta.href} className="data-viz-section__center-button" />
        </div>
      </div>
    </section>
  );
}
