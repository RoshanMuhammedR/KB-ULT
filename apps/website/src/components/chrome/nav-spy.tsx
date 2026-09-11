"use client";

import { useRef, useState } from "react";
import { gsap, ScrollTrigger, useGSAP } from "@/lib/gsap";
import { NAV_SPY } from "@/lib/content";
import { SmartLink } from "@/components/ui/smart-link";

/**
 * The section index in the bottom-left corner. The current section's label fills with the
 * accent as you read through it; it stays out of the way over the hero and the footer, and
 * darkens over the light sections.
 */
export function NavSpy() {
  const ref = useRef<HTMLElement>(null);
  const [active, setActive] = useState<string | null>(null);
  const [hidden, setHidden] = useState(true);
  const [light, setLight] = useState(false);

  useGSAP(
    () => {
      const root = ref.current;
      if (!root) return;
      const sections = gsap.utils.toArray<HTMLElement>(".js-section-spy");
      const links = sections.map((section) => root.querySelector<HTMLElement>(`[data-spy="${section.id}"]`));
      const resetOthers = (keep: number) =>
        links.forEach((link, index) => index !== keep && link?.style.setProperty("--scroll-progress", "0"));

      sections.forEach((section, index) => {
        ScrollTrigger.create({
          trigger: section,
          start: "top center",
          end: "bottom bottom",
          refreshPriority: -1,
          onEnter: () => {
            setActive(section.id);
            resetOthers(index);
          },
          onEnterBack: () => {
            setActive(section.id);
            resetOthers(index);
          },
          onUpdate: (self) => links[index]?.style.setProperty("--scroll-progress", String(self.progress))
        });
      });

      const hero = document.querySelector(".js-main-hero");
      if (hero) {
        ScrollTrigger.create({
          trigger: hero,
          start: "top top",
          end: "bottom top",
          refreshPriority: -1,
          onLeave: () => setHidden(false),
          onEnterBack: () => setHidden(true)
        });
      }
      const content = document.querySelector(".js-page-content");
      if (content) {
        ScrollTrigger.create({
          trigger: content,
          start: "bottom bottom",
          end: "bottom top",
          refreshPriority: -1,
          onEnter: () => setHidden(true),
          onLeaveBack: () => setHidden(false),
          onEnterBack: () => setHidden(true)
        });
      }

      // Adjacent light sections hand over on the same frame, so count rather than toggle.
      const lit = new Set<Element>();
      document.querySelectorAll("[data-surface='light']").forEach((section) => {
        ScrollTrigger.create({
          trigger: section,
          start: "top center",
          end: "bottom center",
          refreshPriority: -1,
          onToggle: (self) => {
            if (self.isActive) lit.add(section);
            else lit.delete(section);
            setLight(lit.size > 0);
          }
        });
      });
    },
    { scope: ref }
  );

  return (
    <nav
      ref={ref}
      className={["nav-spy", hidden ? "is-hidden" : "", light ? "light" : ""].filter(Boolean).join(" ")}
      aria-label="Sections"
    >
      <ul className="nav-spy__list">
        {NAV_SPY.map((item) => (
          <li key={item.id} className="nav-spy__item">
            <SmartLink
              href={`#${item.id}`}
              data-spy={item.id}
              className={`nav-spy__link${active === item.id ? " is-active" : ""}`}
              aria-current={active === item.id ? "true" : undefined}
            >
              {item.label}
            </SmartLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
