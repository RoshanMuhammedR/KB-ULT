"use client";

import { useRef } from "react";
import { gsap, SplitText, useGSAP } from "@/lib/gsap";
import { HERO, SECTION } from "@/lib/content";
import { rich } from "@/lib/rich";
import { usePageState } from "@/components/providers/page-state";
import { PixelIcon } from "@/components/ui/pixel-icon";
import { SmartLink } from "@/components/ui/smart-link";
import { createHeroTube } from "@/components/webgl/hero-tube";
import { useThreeScene } from "@/components/webgl/use-three-scene";
import { HeroTerminal } from "./hero-terminal";

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const { visible } = usePageState();

  // Held in place while the page slides up over it, drifting upward a little itself.
  useGSAP(
    () => {
      const hero = ref.current;
      if (!hero) return;
      gsap
        .timeline({
          scrollTrigger: {
            trigger: hero,
            start: "top top",
            end: "bottom top",
            pin: true,
            scrub: true,
            pinSpacing: false,
            invalidateOnRefresh: true
          }
        })
        .to(hero, { yPercent: -20, ease: "none" });
    },
    { scope: ref }
  );

  // The intro waits for the loader to hand over.
  useGSAP(
    () => {
      const hero = ref.current;
      if (!hero || !visible) return;
      const description = hero.querySelector<HTMLElement>(".js-description");
      const title = hero.querySelector<HTMLElement>(".js-title");
      const scroll = hero.querySelector<HTMLElement>(".main-hero__scroll");
      if (!description || !title || !scroll) return;

      SplitText.create([description, title], {
        type: "words,chars",
        tag: "span",
        wordsClass: "word",
        charsClass: "char",
        autoSplit: true,
        onSplit() {
          const chars = title.querySelectorAll(".char");
          return gsap
            .timeline()
            .from(description.querySelectorAll(".word"), {
              opacity: 0,
              ease: "bounce.inOut",
              stagger: { amount: 0.5, from: "random" }
            }, 0)
            .from(description, { yPercent: 100, ease: "power4", duration: 1.25 }, 0)
            .from([title, scroll], { y: 50, ease: "power4.inOut", duration: 1.75 }, 0)
            .from(scroll, { opacity: 0, ease: "power4.inOut", duration: 1.25 }, 0)
            .from(chars, { opacity: 0, ease: "power4.inOut", stagger: 0.02 }, 0.2)
            .from(chars, { y: 30, ease: "power4", stagger: 0.02 }, 0.25);
        }
      });
    },
    { scope: ref, dependencies: [visible], revertOnUpdate: true }
  );

  return (
    <header ref={ref} className="main-hero js-main-hero">
      <div className="main-hero__description-wrap">
        <p className="t-lg main-hero__description js-description">{rich(HERO.description)}</p>
      </div>
      <div className="main-hero__media">
        <HeroTube />
      </div>
      <HeroTerminal />
      <div className="main-hero__footer">
        <h1 className="t-2xl main-hero__title js-title">{rich(HERO.title)}</h1>
        <SmartLink className="main-hero__scroll" href={`#${SECTION.about}`}>
          <span className="main-hero__scroll-label t-eye-xs">{HERO.scrollLabel}</span>
          <span className="main-hero__scroll-icon">
            <PixelIcon name="arrowDown" />
          </span>
        </SmartLink>
      </div>
    </header>
  );
}

function HeroTube() {
  const ref = useRef<HTMLDivElement>(null);
  useThreeScene(ref, createHeroTube, { maxPixelRatio: 1.5 });
  return <div ref={ref} className="webgl" aria-hidden="true" />;
}
