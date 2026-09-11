"use client";

import { useRef } from "react";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/gsap";
import { ABOUT_CARD } from "@/lib/content";

const TYPE_SPEED = 0.022; // seconds per character

/**
 * Beside the statement, an answer the way Saga gives one back - a sentence, its citation, and
 * the passage the citation points at with the words it rests on underlined - and under it a
 * question the library can't answer, marked as such. Plain type against a hairline. It types
 * itself out once, as the statement comes up; its markup is the finished block, which is what
 * reduced motion keeps.
 */
export function AboutCard() {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const root = ref.current;
      const section = root?.closest(".about-section");
      if (!root || !section || prefersReducedMotion()) return;
      const answer = root.querySelector<HTMLElement>(".js-card-answer");
      const marker = root.querySelector<HTMLElement>(".js-card-marker");
      const source = root.querySelector<HTMLElement>(".js-card-source");
      const file = root.querySelector<HTMLElement>(".js-card-file");
      const foot = root.querySelector<HTMLElement>(".js-card-foot");
      const verdict = root.querySelector<HTMLElement>(".js-card-verdict");
      if (!answer || !marker || !source || !file || !foot || !verdict) return;

      const typed = { count: 0 };
      const type = () => {
        answer.textContent = ABOUT_CARD.answer.slice(0, Math.round(typed.count));
      };
      type();
      gsap.set([marker, source, foot], { opacity: 0 });
      gsap.set(root, { autoAlpha: 0, "--mark": 0 });

      gsap
        .timeline({ scrollTrigger: { trigger: section, start: "top top+=18%", once: true } })
        .fromTo(root, { autoAlpha: 0, x: 16 }, { autoAlpha: 1, x: 0, duration: 0.6, ease: "power3.out" }, 0.2)
        .to(typed, { count: ABOUT_CARD.answer.length, duration: ABOUT_CARD.answer.length * TYPE_SPEED, ease: "none", onUpdate: type }, 0.5)
        .to(marker, { keyframes: [{ opacity: 1, duration: 0.05 }, { opacity: 0.2, duration: 0.08 }, { opacity: 1, duration: 0.1 }] })
        .to(source, { opacity: 1, duration: 0.3 }, ">+0.1")
        .to(file, { duration: 0.6, ease: "none", scrambleText: { text: ABOUT_CARD.citation.file, chars: "abcdefghijklmnopqrstuvwxyz0123456789-", speed: 1 } }, "<")
        .to(root, { "--mark": 1, duration: 0.8, ease: "power2.inOut" }, ">-0.2")
        .to(foot, { opacity: 1, duration: 0.3 }, ">+0.2")
        .to(verdict, { duration: 0.5, ease: "none", scrambleText: { text: ABOUT_CARD.insufficient.verdict, chars: "01", speed: 1 } }, "<");
    },
    { scope: ref }
  );

  const { citation, insufficient } = ABOUT_CARD;
  return (
    <div ref={ref} className="about-card" aria-hidden="true">
      <p className="about-card__answer">
        <span className="js-card-answer">{ABOUT_CARD.answer}</span>{" "}
        <span className="about-card__marker js-card-marker">{citation.marker}</span>
      </p>
      <div className="about-card__source js-card-source">
        <p className="about-card__meta">
          <span className="about-card__tag">{citation.marker}</span>
          <span className="about-card__file js-card-file">{citation.file}</span>
          <span>· {citation.meta}</span>
        </p>
        <p className="about-card__quote">
          {citation.before}
          <mark>{citation.mark}</mark>
          {citation.after}
        </p>
      </div>
      <div className="about-card__foot js-card-foot">
        <p className="about-card__question">
          <span className="about-card__prompt">&gt;</span>
          {insufficient.question}
        </p>
        <p className="about-card__verdict js-card-verdict">{insufficient.verdict}</p>
      </div>
    </div>
  );
}
