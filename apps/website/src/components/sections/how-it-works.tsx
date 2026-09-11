"use client";

import { useRef } from "react";
import { fontsReady, gsap, SplitText, useGSAP } from "@/lib/gsap";
import { HOW_IT_WORKS, SECTION, type Step } from "@/lib/content";
import { InteractiveGrid } from "@/components/ui/interactive-grid";
import { PixelPattern } from "@/components/ui/pixel-pattern";
import { StepMedia } from "./step-media";

/**
 * The three steps. The section holds while you read it, then light pixels flood it and it
 * gives way to the library underneath.
 */
export function HowItWorks() {
  const ref = useRef<HTMLElement>(null);

  useGSAP(
    (_, contextSafe) => {
      const section = ref.current;
      if (!section || !contextSafe) return;
      const container = section.querySelector<HTMLElement>(".services-section__container");
      const title = section.querySelector<HTMLElement>(".services-section__title");
      const text = section.querySelector<HTMLElement>(".services-section__text");
      const cards = section.querySelectorAll(".js-service-card");
      const pixels = section.querySelectorAll(".js-pixel-rect");
      if (!container || !title || !text) return;

      let live = true;
      fontsReady().then(
        contextSafe(() => {
          if (!live) return;
          SplitText.create([title, text], {
            type: "lines,words,chars",
            mask: "lines",
            linesClass: "line",
            wordsClass: "word",
            charsClass: "char",
            autoSplit: true,
            onSplit() {
              return gsap
                .timeline({ scrollTrigger: { trigger: section, start: "top top", once: true } })
                .from(title.querySelectorAll(".word"), { yPercent: 100, duration: 0.5, ease: "power2" }, 0)
                .from(text.querySelectorAll(".char"), { opacity: 0, stagger: 0.007, ease: "power2" }, 0)
                .from(title.querySelectorAll(".char"), { opacity: 0, stagger: 0.01, ease: "power2" }, 0.1)
                .from(text.querySelectorAll(".word"), { yPercent: 100, duration: 0.3, ease: "power2" }, 0.1)
                .from(cards, { opacity: 0, yPercent: 30, duration: 1, stagger: 0.1, ease: "power4.inOut" }, 0.1);
            }
          });
        })
      );

      const media = gsap.matchMedia();
      media.add({ desktop: "(min-width: 1025px)", mobile: "(max-width: 1024px)" }, (context) => {
        const { desktop } = context.conditions as { desktop: boolean };
        gsap
          .timeline({
            scrollTrigger: {
              trigger: container,
              endTrigger: section,
              // Held from the top when it fits the screen, else from its bottom edge, so no step
              // is ever held below the fold.
              start: desktop ? () => (container.offsetHeight > window.innerHeight ? "bottom bottom" : "top top") : "bottom bottom",
              end: "bottom top",
              pin: true,
              scrub: true,
              id: SECTION.howItWorks,
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
    <section ref={ref} id={SECTION.howItWorks} className="services-section js-section-spy">
      <div className="services-section__container">
        <PixelPattern surface="light" />
        <InteractiveGrid />
        <div className="services-section__inner">
          <div className="services-section__head">
            <h2 className="t-2xl services-section__title">{HOW_IT_WORKS.title}</h2>
            <p className="t-md services-section__text">{HOW_IT_WORKS.text}</p>
          </div>
          <div className="services-section__content">
            {HOW_IT_WORKS.steps.map((step) => (
              <StepCard key={step.index} step={step} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

const wrapAngle = (angle: number) => ((((angle + 180) % 360) + 360) % 360) - 180;
// The conic sweep peaks this far clockwise of its start; turning by it aims the peak.
const SWEEP_PEAK = 36;

function StepCard({ step }: { step: Step }) {
  const ref = useRef<HTMLElement>(null);

  // The lit edge turns to face the pointer, taking the short way round.
  useGSAP(
    () => {
      const card = ref.current;
      const glow = card?.querySelector<HTMLElement>(".service-card__bg");
      if (!card || !glow) return;
      let angle = 0;
      let turning: gsap.core.Tween | null = null;

      const enter = () => gsap.to(glow, { opacity: 1, duration: 0.3, ease: "power2.out" });
      const exit = () => {
        gsap.to(glow, { opacity: 0, duration: 0.3, ease: "power2.out" });
        angle = 0;
      };
      const move = (event: PointerEvent) => {
        const box = card.getBoundingClientRect();
        const pointer = (Math.atan2(event.clientY - box.top - box.height / 2, event.clientX - box.left - box.width / 2) * 180) / Math.PI;
        const next = angle + wrapAngle(pointer + SWEEP_PEAK - angle);
        if (!turning || turning.progress() > 0.5) angle = next;
        turning?.kill();
        turning = gsap.to(glow, { "--rotate": `${next}deg`, duration: 0.6, ease: "power1.out", overwrite: "auto" });
      };

      card.addEventListener("pointerenter", enter);
      card.addEventListener("pointerleave", exit);
      card.addEventListener("pointermove", move);
      return () => {
        card.removeEventListener("pointerenter", enter);
        card.removeEventListener("pointerleave", exit);
        card.removeEventListener("pointermove", move);
      };
    },
    { scope: ref }
  );

  return (
    <article ref={ref} className="service-card js-service-card">
      <span className="service-card__pin" aria-hidden="true" />
      <span className="service-card__pin" aria-hidden="true" />
      <span className="service-card__pin" aria-hidden="true" />
      <span className="service-card__pin" aria-hidden="true" />
      <div className="service-card__bg" aria-hidden="true" />
      <div className="service-card__media-wrap">
        <StepMedia kind={step.media} />
      </div>
      <div className="service-card__content">
        <div className="service-card__head">
          <h3 className="t-2lg service-card__title">{step.title}</h3>
          <span className="service-card__label">[{step.index}]</span>
        </div>
        <p className="t-md service-card__text">{step.text}</p>
      </div>
    </article>
  );
}
