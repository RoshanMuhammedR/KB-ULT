"use client";

import { useEffect, useRef, useState } from "react";
import { fontsReady, gsap, SplitText, useGSAP } from "@/lib/gsap";
import { PRIVACY, SECTION } from "@/lib/content";
import { rich } from "@/lib/rich";
import { Button } from "@/components/ui/button";
import { InteractiveGrid } from "@/components/ui/interactive-grid";
import { PixelIcon } from "@/components/ui/pixel-icon";

/**
 * Four guarantees, as an index: hover (or focus) one and its detail settles in the corner,
 * with its mark pinned beside it. On narrow screens the four become a row of cards.
 */
export function Privacy() {
  const ref = useRef<HTMLElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<string>(PRIVACY.items[0].index);
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
      const title = section?.querySelector<HTMLElement>(".testimonial-section__title");
      if (!section || !title || !contextSafe) return;

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
                .timeline({ scrollTrigger: { trigger: section, start: "top top+=40%", once: true } })
                .from(self.chars, { opacity: 0, stagger: 0.008, ease: "power2" })
          });
        })
      );

      const contents = section.querySelector(".testimonial-section__contents");
      if (desktop && contents) {
        const items = section.querySelectorAll(".js-privacy-item");
        gsap.set([items, contents], { opacity: 0 });
        const timeline = gsap
          .timeline({ scrollTrigger: { trigger: section, start: "top top+=55%", once: true } })
          .to(items, { opacity: 1, stagger: 0.08, ease: "power2.inOut", clearProps: "opacity" });
        section.querySelectorAll<HTMLElement>(".js-privacy-index").forEach((element, i) => {
          const text = element.textContent ?? "";
          timeline.to(element, { scrambleText: { text, chars: "0123456789", speed: 2 } }, 0.125 + i * 0.08);
        });
        section.querySelectorAll<HTMLElement>(".js-privacy-title").forEach((element, i) => {
          const text = element.textContent ?? "";
          timeline.to(element, { scrambleText: { text, chars: text.replace(/\s/g, ""), speed: 2 } }, 0.25 + i * 0.08);
        });
        timeline.to(contents, { opacity: 1, duration: 0.8, ease: "power2.inOut", clearProps: "opacity" }, 0.25);
      }

      return () => {
        live = false;
      };
    },
    { scope: ref, dependencies: [desktop], revertOnUpdate: true }
  );

  const step = (direction: 1 | -1) => {
    const track = trackRef.current;
    const card = track?.firstElementChild as HTMLElement | null;
    if (!track || !card) return;
    track.scrollBy({ left: direction * (card.offsetWidth + 20), behavior: "smooth" });
  };

  return (
    <section ref={ref} id={SECTION.privacy} className="testimonial-section light js-section-spy" data-surface="light">
      <InteractiveGrid />
      <div className="testimonial-section__container">
        <div className="testimonial-section__head">
          <h2 className="t-2xl testimonial-section__title">{rich(PRIVACY.title)}</h2>
        </div>
        <div className="testimonial-section__content">
          {desktop ? (
            <div className="testimonial-section__desktop">
              <div className="testimonial-section__items">
                <ul className="testimonial-section__list">
                  {PRIVACY.items.map((item) => (
                    <li
                      key={item.index}
                      className={`testimonial-section__item js-privacy-item${active === item.index ? " is-active" : ""}`}
                      onMouseEnter={() => setActive(item.index)}
                    >
                      <button
                        type="button"
                        className="testimonial-section__item-link"
                        aria-pressed={active === item.index}
                        aria-controls={`privacy-${item.index}`}
                        onFocus={() => setActive(item.index)}
                        onClick={() => setActive(item.index)}
                      >
                        <span className="t-xl testimonial-section__item-index js-privacy-index">{item.index}</span>
                        <span className="t-xl testimonial-section__item-title js-privacy-title">{item.title}</span>
                        <span className="testimonial-section__item-icon" aria-hidden="true">
                          <PixelIcon name="arrow" />
                        </span>
                      </button>
                      <div className="testimonial-section__item-logo-wrap" aria-hidden="true">
                        <PixelIcon name={item.icon} />
                        <span className="testimonial-section__item-logo-pin" />
                        <span className="testimonial-section__item-logo-pin" />
                        <span className="testimonial-section__item-logo-pin" />
                        <span className="testimonial-section__item-logo-pin" />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="testimonial-section__contents">
                {PRIVACY.items.map((item) => (
                  <div
                    key={item.index}
                    id={`privacy-${item.index}`}
                    className={`testimonial-section__content-group${active === item.index ? " is-active" : ""}`}
                  >
                    <p className="t-md testimonial-section__content-text">{item.text}</p>
                    <p className="t-eye-xs testimonial-section__content-author">
                      {PRIVACY.byline} / {item.index}
                    </p>
                  </div>
                ))}
              </div>
            </div>
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
      </div>
    </section>
  );
}
