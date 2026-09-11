"use client";

import type { ComponentPropsWithRef, MouseEvent } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";
import { scrollToSection, useLenis } from "@/components/providers/smooth-scroll";

/**
 * Leave the page the way the page arrives: fade the whole document out, then navigate.
 *
 * Everything this site links to outside itself is a full navigation - the product app lives
 * under /app as a separate Next app (Caddy routes it), so client-side routing cannot reach it.
 */
export function leave(href: string) {
  const node = document.querySelector(".transition__container");
  if (!node || prefersReducedMotion()) {
    window.location.assign(href);
    return;
  }
  gsap.to(node, {
    opacity: 0,
    duration: 0.25,
    ease: "power1.inOut",
    onComplete: () => window.location.assign(href)
  });
}

/**
 * An anchor that knows where it is going. `#section` links scroll smoothly to the section
 * (or, on a page without it, go home to it); everything else fades out and navigates.
 * Modified clicks and new-tab links keep the browser's own behaviour.
 */
export function SmartLink({ href = "", onClick, ...props }: ComponentPropsWithRef<"a">) {
  const lenis = useLenis();

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      props.target === "_blank"
    ) {
      return;
    }
    event.preventDefault();
    if (href.startsWith("#")) {
      const target = document.getElementById(href.slice(1));
      if (target) scrollToSection(target, lenis);
      else leave(`/${href}`);
      return;
    }
    leave(href);
  };

  return <a href={href} onClick={handleClick} {...props} />;
}
