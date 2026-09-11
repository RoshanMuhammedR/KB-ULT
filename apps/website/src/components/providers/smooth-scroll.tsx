"use client";

import Lenis from "lenis";
import { createContext, useContext, useEffect, useState } from "react";
import { gsap, prefersReducedMotion, ScrollTrigger } from "@/lib/gsap";
import { SECTION } from "@/lib/content";
import { usePageState } from "./page-state";

const LenisContext = createContext<Lenis | null>(null);

export const useLenis = () => useContext(LenisContext);

/**
 * Smooth scrolling for the whole document, driven from gsap's ticker so ScrollTrigger and
 * Lenis read the same scroll position on the same frame. It starts stopped: the loader
 * holds the page at the top until it hands over.
 */
export function SmoothScroll({ children }: { children: React.ReactNode }) {
  const { visible } = usePageState();
  const [lenis, setLenis] = useState<Lenis | null>(null);

  useEffect(() => {
    ScrollTrigger.clearScrollMemory("manual");
    window.scrollTo(0, 0);

    const instance = new Lenis({ lerp: 0.1, smoothWheel: !prefersReducedMotion(), autoRaf: false });
    instance.stop();
    instance.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => instance.raf(time * 1000);
    gsap.ticker.add(tick);
    setLenis(instance);

    return () => {
      gsap.ticker.remove(tick);
      instance.destroy();
      setLenis(null);
    };
  }, []);

  useEffect(() => {
    if (!visible || !lenis) return;
    lenis.start();
    ScrollTrigger.refresh();
    // A deep link (/#library) lands on its section once the page is revealed.
    const target = window.location.hash ? document.getElementById(window.location.hash.slice(1)) : null;
    if (target) scrollToSection(target, lenis, true);
  }, [visible, lenis]);

  return <LenisContext.Provider value={lenis}>{children}</LenisContext.Provider>;
}

/**
 * Scroll to a section, landing where it reads best rather than where it starts.
 *
 * Several sections are pinned and play a timeline while pinned, so their top edge is often
 * the wrong place to stop: the library is only legible once its fade-in has played, and the
 * closing call only once its circles have opened. Scrolling down lands at the end of such a
 * section's pin; scrolling back up lands at its start.
 */
export function scrollToSection(target: HTMLElement | null, lenis: Lenis | null, immediate = false) {
  if (!target) return;
  ScrollTrigger.refresh();
  const trigger = ScrollTrigger.getById(target.id);
  let top = window.scrollY + target.getBoundingClientRect().top;
  if (trigger) {
    if (target.id === SECTION.library) top = trigger.end;
    else if (target.id === SECTION.about) top = trigger.start;
    else if (target.id === SECTION.howItWorks) top = trigger.start + 50;
    else top = window.scrollY < trigger.start ? trigger.end : trigger.start;
  }
  if (lenis) lenis.scrollTo(top, { duration: 1.2, immediate, force: immediate });
  else window.scrollTo({ top, behavior: immediate ? "instant" : "smooth" });
}
