"use client";

import { useRef, type CSSProperties } from "react";
import { gsap, prefersReducedMotion, ScrollTrigger, useGSAP } from "@/lib/gsap";
import { TERMINAL } from "@/lib/content";
import { usePageState } from "@/components/providers/page-state";

const TYPE_SPEED = 0.034; // seconds per character
const HOLD = 4.5; // seconds the finished readout stays up

/**
 * The hero's readout: the demo question typed into Saga, the library searched, and the
 * passages that cleared the bar ranked in with their pages and scores - plain type against a
 * hairline, on a loop while the hero is on screen. Its markup is the finished readout, which
 * is what reduced motion keeps.
 */
export function HeroTerminal() {
  const ref = useRef<HTMLDivElement>(null);
  const { visible } = usePageState();

  useGSAP(
    () => {
      const root = ref.current;
      if (!root || prefersReducedMotion()) return;
      // Out of sight under the loader; it comes in once the page is handed over.
      if (!visible) {
        gsap.set(root, { autoAlpha: 0 });
        return;
      }
      const body = root.querySelector<HTMLElement>(".js-term-body");
      const question = root.querySelector<HTMLElement>(".js-term-question");
      const search = root.querySelector<HTMLElement>(".js-term-search");
      const percent = root.querySelector<HTMLElement>(".js-term-percent");
      const verdict = root.querySelector<HTMLElement>(".js-term-verdict");
      const rows = gsap.utils.toArray<HTMLElement>(".js-term-row", root);
      if (!body || !question || !search || !percent || !verdict) return;

      const typed = { count: 0 };
      const searched = { progress: 0 };
      const type = () => {
        question.textContent = TERMINAL.question.slice(0, Math.round(typed.count));
      };
      const meter = () => {
        search.style.setProperty("--progress", String(searched.progress));
        percent.textContent = `${Math.round(searched.progress * 100)}%`;
      };

      gsap.fromTo(root, { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.8, delay: 0.6, ease: "power3.out" });

      const loop = gsap.timeline({ repeat: -1, delay: 1.2 });
      loop
        .call(() => {
          typed.count = 0;
          searched.progress = 0;
          type();
          meter();
        })
        .set(body, { opacity: 1 })
        .set([search, verdict, ...rows], { opacity: 0 })
        .to(typed, { count: TERMINAL.question.length, duration: TERMINAL.question.length * TYPE_SPEED, ease: "none", onUpdate: type }, 0.2)
        .addLabel("search", ">+0.35")
        .to(search, { opacity: 1, duration: 0.2 }, "search")
        .to(searched, { progress: 1, duration: 1.4, ease: "power1.inOut", onUpdate: meter }, "search")
        .addLabel("rank", ">");

      rows.forEach((row, i) => {
        const file = row.querySelector<HTMLElement>(".js-term-file");
        const score = row.querySelector<HTMLElement>(".js-term-score");
        const passage = TERMINAL.passages[i];
        if (!file || !score || !passage) return;
        const counter = { value: 0 };
        const at = `rank+=${0.15 + i * 0.4}`;
        loop
          .fromTo(row, { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.3, ease: "power2.out", immediateRender: false }, at)
          .to(file, { duration: 0.5, ease: "none", scrambleText: { text: passage.file, chars: "abcdefghijklmnopqrstuvwxyz0123456789-", speed: 1 } }, at)
          .fromTo(
            counter,
            { value: 0 },
            {
              value: passage.score,
              duration: 0.7,
              ease: "power2.out",
              immediateRender: false,
              onUpdate: () => {
                score.textContent = `${Math.round(counter.value)}%`;
              }
            },
            at
          );
      });

      loop
        .addLabel("cite", ">+0.1")
        .to(verdict, { opacity: 1, duration: 0.2 }, "cite")
        .to(verdict, { duration: 0.6, ease: "none", scrambleText: { text: TERMINAL.verdict, chars: "01", speed: 1 } }, "cite")
        .to(body, { opacity: 0, duration: 0.5, ease: "power2.in" }, `>+${HOLD}`);

      // It only runs while the hero is on screen.
      const hero = root.closest(".main-hero");
      if (hero) {
        ScrollTrigger.create({
          trigger: hero,
          start: "top top",
          end: "bottom top",
          onLeave: () => loop.pause(),
          onEnterBack: () => loop.resume()
        });
      }
    },
    { scope: ref, dependencies: [visible], revertOnUpdate: true }
  );

  return (
    <div className="hero-terminal-wrap">
      <div ref={ref} className="hero-terminal" aria-hidden="true">
        <div className="hero-terminal__body js-term-body">
          <p className="hero-terminal__query">
            <span className="hero-terminal__prompt">&gt;</span>
            <span className="js-term-question">{TERMINAL.question}</span>
            <span className="hero-terminal__caret" />
          </p>
          <div className="hero-terminal__search js-term-search" style={{ "--progress": 1 } as CSSProperties}>
            <span>{TERMINAL.search}</span>
            <span className="js-term-percent">100%</span>
            <span className="hero-terminal__meter" />
          </div>
          <ul className="hero-terminal__rows">
            {TERMINAL.passages.map((passage) => (
              <li key={`${passage.file}-${passage.locator}`} className="hero-terminal__row js-term-row">
                <span className="hero-terminal__locator">{passage.locator}</span>
                <span className="hero-terminal__file js-term-file">{passage.file}</span>
                <span className="hero-terminal__score js-term-score">{passage.score}%</span>
              </li>
            ))}
          </ul>
          <p className="hero-terminal__verdict js-term-verdict">{TERMINAL.verdict}</p>
        </div>
      </div>
    </div>
  );
}
