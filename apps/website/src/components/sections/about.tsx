"use client";

import { useRef } from "react";
import { fontsReady, gsap, SplitText, useGSAP } from "@/lib/gsap";
import { ABOUT, SECTION } from "@/lib/content";
import { rich } from "@/lib/rich";
import { InteractiveGrid } from "@/components/ui/interactive-grid";
import { PixelPattern } from "@/components/ui/pixel-pattern";
import { Grounding } from "./grounding";

/**
 * The statement, on the light panel that slides up over the hero. It holds for two and a
 * half screens, then dissolves pixel by pixel into the dark of the grounding scene below.
 */
export function About() {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(
    (_, contextSafe) => {
      const root = ref.current;
      const section = root?.querySelector<HTMLElement>(".about-section");
      const title = root?.querySelector<HTMLElement>(".about-section__title");
      if (!section || !title || !contextSafe) return;
      const pixels = section.querySelectorAll(".js-pixel-rect");

      let live = true;
      fontsReady().then(
        contextSafe(() => {
          if (!live) return;
          SplitText.create(title, {
            type: "lines,words,chars",
            mask: "lines",
            linesClass: "line",
            wordsClass: "word",
            charsClass: "char",
            autoSplit: true,
            onSplit(self) {
              const timeline = gsap.timeline({ scrollTrigger: { trigger: section, start: "top top+=18%", once: true } });
              self.lines.forEach((line, index) => {
                timeline
                  .from(line.querySelectorAll(".word"), { yPercent: 100, duration: 0.5, ease: "power2" }, 0.1 * index)
                  .from(line.querySelectorAll(".char"), { opacity: 0, stagger: 0.01, ease: "power2" }, 0.1 * index);
              });
              return timeline;
            }
          });
        })
      );

      const media = gsap.matchMedia();
      media.add({ desktop: "(min-width: 768px)", mobile: "(max-width: 767px)" }, (context) => {
        const { desktop } = context.conditions as { desktop: boolean };
        gsap
          .timeline({
            scrollTrigger: {
              trigger: section,
              start: "top top",
              end: "bottom top",
              pin: true,
              scrub: true,
              id: SECTION.about,
              pinSpacing: false,
              invalidateOnRefresh: true
            }
          })
          .to(pixels, { opacity: 1, duration: 0.01, stagger: { each: desktop ? 0.025 : 0.06, from: "random" } }, desktop ? 9 : 11)
          .set(section, { opacity: 0 });
      });

      return () => {
        live = false;
        media.revert();
      };
    },
    { scope: ref }
  );

  return (
    <div id={SECTION.about} ref={ref} className="js-section-spy">
      <section className="about-section light" data-surface="light">
        <div className="about-section__container">
          <PixelPattern surface="dark" />
          <InteractiveGrid />
          <h2 className="t-xl about-section__title">{rich(ABOUT)}</h2>
        </div>
      </section>
      <Grounding />
    </div>
  );
}
