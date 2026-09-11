import gsap from "gsap";
import { ScrambleTextPlugin } from "gsap/ScrambleTextPlugin";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";
import { useGSAP } from "@gsap/react";

// Registered once, here, rather than in every component that animates: registration is
// idempotent, but a plugin used before anyone registers it fails silently.
if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger, SplitText, ScrambleTextPlugin, useGSAP);
  // Lenis drives the scroll from gsap's ticker; lag smoothing would make the two disagree
  // for a frame after every stall.
  gsap.ticker.lagSmoothing(0);
}

export { gsap, ScrollTrigger, SplitText, useGSAP };

/**
 * Split text is cut into lines once, from where the words fall at that moment - so cut it in
 * the real font, not in the fallback it swaps out. Lines measured in the narrower fallback
 * overflow once the webfont lands, and each one sheds its last word onto a line of its own.
 */
export const fontsReady = () =>
  typeof document !== "undefined" && document.fonts ? document.fonts.ready : Promise.resolve();

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
