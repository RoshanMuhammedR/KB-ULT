"use client";

import { useEffect, useRef, useState } from "react";
import { fontsReady, gsap, prefersReducedMotion, ScrollTrigger, SplitText, useGSAP } from "@/lib/gsap";
import { PRIVACY, SECTION } from "@/lib/content";
import { rich } from "@/lib/rich";
import { useLenis } from "@/components/providers/smooth-scroll";
import { Button } from "@/components/ui/button";
import { InteractiveGrid } from "@/components/ui/interactive-grid";
import { PixelIcon } from "@/components/ui/pixel-icon";
import { PrivacyScreen } from "./privacy-screen";

const COUNT = PRIVACY.items.length;
// Screens of scroll the section is held for, all four guarantees together.
const HOLD = COUNT * 0.75;

/**
 * Four guarantees, held on screen while you scroll through them: each takes its turn in the
 * index, its mark redraws on the screen beside it a pixel at a time and a scan runs down it.
 * Picking one scrolls to it. On narrow screens the four become a row of cards.
 */
export function Privacy() {
  const ref = useRef<HTMLElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const holdRef = useRef<ScrollTrigger | null>(null);
  const lenis = useLenis();
  const [active, setActive] = useState(0);
  const [desktop, setDesktop] = useState(true);

  useEffect(() => {
    const query = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktop(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useGSAP(
    (_, contextSafe) => {
      const section = ref.current;
      const frame = section?.querySelector<HTMLElement>(".testimonial-section__frame");
      const title = section?.querySelector<HTMLElement>(".testimonial-section__title");
      if (!section || !frame || !title || !contextSafe) return;

      let live = true;
      fontsReady().then(
        contextSafe(() => {
          if (!live) return;
          SplitText.create(title, {
            type: "lines,words,chars",
            linesClass: "line",
            wordsClass: "word",
            charsClass: "char",
            autoSplit: true,
            onSplit: (self) =>
              gsap
                .timeline({ scrollTrigger: { trigger: section, start: "top 60%", once: true } })
                .from(self.chars, { opacity: 0, stagger: 0.008, ease: "power2" })
          });
        })
      );

      if (desktop) {
        const segments = section.querySelectorAll<HTMLElement>(".js-privacy-segment");
        const screen = section.querySelector<HTMLElement>(".js-privacy-screen");
        let current = 0;
        holdRef.current = ScrollTrigger.create({
          trigger: frame,
          start: "top top",
          end: () => `+=${window.innerHeight * HOLD}`,
          pin: true,
          invalidateOnRefresh: true,
          onUpdate(self) {
            const steps = self.progress * COUNT;
            const next = Math.min(COUNT - 1, Math.floor(steps));
            if (next !== current) {
              current = next;
              setActive(next);
            }
            segments.forEach((segment, i) => segment.style.setProperty("--fill", String(gsap.utils.clamp(0, 1, steps - i))));
            screen?.style.setProperty("--scan", String(gsap.utils.clamp(0, 1, steps - next)));
          }
        });

        // The screen powers on as the section comes up - a line that opens into a picture -
        // and the index tunes in beside it.
        if (!prefersReducedMotion()) {
          const items = section.querySelectorAll(".js-privacy-item");
          const inner = section.querySelector(".js-privacy-screen-inner");
          gsap.set(items, { opacity: 0 });
          const boot = gsap
            .timeline({ scrollTrigger: { trigger: section, start: "top 55%", once: true } })
            .fromTo(inner, { scaleX: 0.3, scaleY: 0.005, opacity: 0 }, { scaleX: 1, opacity: 1, duration: 0.3, ease: "power2.out" }, 0)
            .to(inner, { scaleY: 1, duration: 0.45, ease: "power3.out" }, 0.3)
            .to(items, { opacity: 1, stagger: 0.08, ease: "power2.inOut", clearProps: "opacity" }, 0.15);
          section.querySelectorAll<HTMLElement>(".js-privacy-index").forEach((element, i) => {
            const text = element.textContent ?? "";
            boot.to(element, { scrambleText: { text, chars: "0123456789", speed: 2 } }, 0.25 + i * 0.08);
          });
          section.querySelectorAll<HTMLElement>(".js-privacy-title").forEach((element, i) => {
            const text = element.textContent ?? "";
            boot.to(element, { scrambleText: { text, chars: text.replace(/\s/g, ""), speed: 2 } }, 0.35 + i * 0.08);
          });
        }
      }

      return () => {
        live = false;
        holdRef.current = null;
      };
    },
    { scope: ref, dependencies: [desktop], revertOnUpdate: true }
  );

  // Picking a guarantee scrolls to its stretch of the hold, so the page and the index agree.
  const select = (index: number) => {
    const hold = holdRef.current;
    if (!hold) {
      setActive(index);
      return;
    }
    const top = hold.start + ((index + 0.5) / COUNT) * (hold.end - hold.start);
    if (lenis) lenis.scrollTo(top, { duration: 1.2 });
    else window.scrollTo({ top, behavior: "smooth" });
  };

  const step = (direction: 1 | -1) => {
    const track = trackRef.current;
    const card = track?.firstElementChild as HTMLElement | null;
    if (!track || !card) return;
    track.scrollBy({ left: direction * (card.offsetWidth + 20), behavior: "smooth" });
  };

  return (
    <section ref={ref} id={SECTION.privacy} className="testimonial-section light js-section-spy" data-surface="light">
      <div className="testimonial-section__frame">
        <InteractiveGrid />
        <div className="testimonial-section__container">
          <div className="testimonial-section__copy">
            <div className="testimonial-section__head">
              <h2 className="t-2xl testimonial-section__title">{rich(PRIVACY.title)}</h2>
            </div>
            {desktop ? (
              <>
                <ul className="testimonial-section__list">
                  {PRIVACY.items.map((item, index) => (
                    <li
                      key={item.index}
                      className={`testimonial-section__item js-privacy-item${active === index ? " is-active" : ""}`}
                    >
                      <button
                        type="button"
                        className="testimonial-section__item-link"
                        aria-pressed={active === index}
                        aria-controls={`privacy-${item.index}`}
                        onClick={() => select(index)}
                      >
                        <span className="t-xl testimonial-section__item-index js-privacy-index">{item.index}</span>
                        <span className="t-xl testimonial-section__item-title js-privacy-title">{item.title}</span>
                        <span className="testimonial-section__item-icon" aria-hidden="true">
                          <PixelIcon name="arrow" />
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="testimonial-section__details">
                  {PRIVACY.items.map((item, index) => (
                    <div
                      key={item.index}
                      id={`privacy-${item.index}`}
                      className={`testimonial-section__detail${active === index ? " is-active" : ""}`}
                    >
                      <p className="t-md testimonial-section__detail-text">{item.text}</p>
                      <p className="t-eye-xs testimonial-section__detail-author">
                        {PRIVACY.byline} / {item.index}
                      </p>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="testimonial-section__mobile">
                <div ref={trackRef} className="testimonial-section__mobile-track">
                  {PRIVACY.items.map((item) => (
                    <article key={item.index} className="service-card">
                      <span className="service-card__pin" aria-hidden="true" />
                      <span className="service-card__pin" aria-hidden="true" />
                      <span className="service-card__pin" aria-hidden="true" />
                      <span className="service-card__pin" aria-hidden="true" />
                      <div className="service-card__media-wrap" aria-hidden="true">
                        <PixelIcon name={item.icon} />
                      </div>
                      <div className="service-card__content">
                        <div className="service-card__head">
                          <h3 className="t-2lg service-card__title">{item.title}</h3>
                          <span className="service-card__label">[{item.index}]</span>
                        </div>
                        <p className="t-md service-card__text">{item.text}</p>
                      </div>
                    </article>
                  ))}
                </div>
                <div className="testimonial-section__mobile-controls">
                  <Button variant="light" size="icon" inverted onClick={() => step(-1)} ariaLabel="Previous" />
                  <Button variant="light" size="icon" onClick={() => step(1)} ariaLabel="Next" />
                </div>
              </div>
            )}
          </div>
          {desktop && <PrivacyScreen active={active} />}
        </div>
      </div>
    </section>
  );
}
