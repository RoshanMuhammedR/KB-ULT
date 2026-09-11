"use client";

import { useRef, type MouseEvent } from "react";
import { gsap, useGSAP } from "@/lib/gsap";
import { LIBRARY, SECTION } from "@/lib/content";
import { rich } from "@/lib/rich";
import { PixelIcon } from "@/components/ui/pixel-icon";
import { SmartLink } from "@/components/ui/smart-link";

const SLICES = 37;
const finePointer = () => window.matchMedia("(hover: hover) and (pointer: fine)").matches;

/**
 * The library, as a list of what it holds. The list fades up while the section holds; a row
 * floods with the accent in thin slices from the left when hovered, and drains to the right.
 */
export function Library() {
  const ref = useRef<HTMLElement>(null);

  const { contextSafe } = useGSAP(
    () => {
      const section = ref.current;
      const container = section?.querySelector(".case-histories__container");
      if (!section || !container) return;
      gsap
        .timeline({
          scrollTrigger: {
            trigger: section,
            start: "top top",
            end: "center top",
            pin: true,
            scrub: true,
            id: SECTION.library,
            invalidateOnRefresh: true
          }
        })
        .from(container, { opacity: 0 }, 0);
    },
    { scope: ref }
  );

  const sweep = contextSafe((event: MouseEvent<HTMLLIElement>, fill: boolean) => {
    if (!finePointer()) return;
    const slices = event.currentTarget.querySelectorAll(".js-case-row-rect");
    gsap.set(slices, { transformOrigin: fill ? "0% 50%" : "100% 50%" });
    gsap.to(slices, { scaleX: fill ? 1.05 : 0, stagger: { each: 0.01, from: "start" }, ease: "power4.inOut", overwrite: true });
  });

  return (
    <section ref={ref} id={SECTION.library} className="case-histories light js-section-spy" data-surface="light">
      <div className="case-histories__container">
        <div className="case-histories__head">
          <h2 className="t-2xl case-histories__title">{rich(LIBRARY.title)}</h2>
          <p className="t-md case-histories__text">{rich(LIBRARY.text)}</p>
        </div>
        <ul className="case-histories__items">
          {LIBRARY.rows.map((row) => (
            <li
              key={row.index}
              className="case-histories__item"
              onMouseEnter={(event) => sweep(event, true)}
              onMouseLeave={(event) => sweep(event, false)}
            >
              <SmartLink
                href={LIBRARY.href}
                className="case-histories__item-link"
                aria-label={`${row.title}: ${row.type}, ${row.locator.toLowerCase()}. Start a library of your own.`}
              >
                <div className="case-histories__item-pattern" aria-hidden="true">
                  {Array.from({ length: SLICES }, (_, i) => (
                    <div key={i} className="case-histories__pattern-item js-case-row-rect" />
                  ))}
                </div>
                <p className="t-xl case-histories__item-index">{row.index}</p>
                <p className="t-xl case-histories__item-title">{row.title}</p>
                <p className="t-eye-sm case-histories__item-year">[{row.type}]</p>
                <p className="t-eye-sm case-histories__item-type">{row.locator}</p>
                <div className="case-histories__item-action">
                  <div className="case-histories__item-button">
                    <PixelIcon name="arrow" />
                  </div>
                </div>
              </SmartLink>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
