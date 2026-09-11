"use client";

import { useRef } from "react";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/gsap";
import { PixelIcon } from "./pixel-icon";
import { SmartLink } from "./smart-link";

type ButtonProps = {
  label?: string;
  href?: string;
  onClick?: () => void;
  variant?: "primary" | "light";
  size?: "regular" | "sm" | "icon";
  inverted?: boolean;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
};

/**
 * The dashed, gradient-edged button. On hover its label scrambles back into itself and the
 * arrow slides out as a double chevron slides in.
 */
export function Button({
  label,
  href,
  onClick,
  variant = "primary",
  size = "regular",
  inverted = false,
  disabled = false,
  ariaLabel,
  className = ""
}: ButtonProps) {
  const ref = useRef<HTMLAnchorElement & HTMLButtonElement>(null);

  useGSAP(
    () => {
      const element = ref.current;
      const text = element?.querySelector<HTMLElement>(".button__text");
      if (!element || !text) return;
      const original = text.textContent ?? "";
      const scramble = () => {
        if (gsap.isTweening(text) || prefersReducedMotion()) return;
        gsap.to(text, {
          duration: 0.8,
          ease: "sine.in",
          scrambleText: { text: original, speed: 1, chars: original.replace(/\s/g, "") }
        });
      };
      element.addEventListener("pointerenter", scramble);
      element.addEventListener("focus", scramble);
      return () => {
        element.removeEventListener("pointerenter", scramble);
        element.removeEventListener("focus", scramble);
      };
    },
    { scope: ref }
  );

  const classes = [
    "button",
    `button--${variant}`,
    `button--${size}`,
    inverted ? "button--inverted" : "",
    className
  ]
    .filter(Boolean)
    .join(" ");

  const inner = (
    <>
      {label ? <span className="t-sm button__text">{label}</span> : null}
      <span className="button__icon" aria-hidden="true">
        <span className="button__icon-front">
          <PixelIcon name="arrow" />
        </span>
        <span className="button__icon-back">
          <PixelIcon name="chevrons" />
        </span>
      </span>
    </>
  );

  if (href) {
    return (
      <SmartLink ref={ref} href={href} className={classes} aria-label={ariaLabel}>
        {inner}
      </SmartLink>
    );
  }
  return (
    <button ref={ref} type="button" className={classes} onClick={onClick} disabled={disabled} aria-label={ariaLabel}>
      {inner}
    </button>
  );
}
