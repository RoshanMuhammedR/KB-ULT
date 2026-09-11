"use client";

import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/gsap";
import { FOOTER, NAVIGATION } from "@/lib/content";
import { PixelIcon } from "@/components/ui/pixel-icon";
import { SmartLink } from "@/components/ui/smart-link";
import { createFooterGrid, type FooterGridParams } from "@/components/webgl/footer-grid";
import { useThreeScene } from "@/components/webgl/use-three-scene";

/**
 * The footer lives fixed behind the page. The page ends a full screen early, so the last
 * screen of scrolling lifts it off to reveal this - rising into place over the moving floor.
 */
export function Footer() {
  const ref = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const revealed = useRef(false);
  const params = useRef<FooterGridParams>({ cell: 1 }).current;

  useThreeScene(canvasRef, (renderer, container) => createFooterGrid(renderer, container, params), {
    maxPixelRatio: 1.5,
    isActive: () => revealed.current
  });

  useGSAP(
    () => {
      const footer = ref.current;
      const content = document.querySelector(".js-page-content");
      if (!footer || !content) return;
      gsap
        .timeline({
          scrollTrigger: {
            trigger: content,
            endTrigger: document.documentElement,
            start: "bottom bottom",
            end: "bottom bottom",
            scrub: true,
            invalidateOnRefresh: true,
            refreshPriority: -1,
            onEnter: () => (revealed.current = true),
            onLeaveBack: () => (revealed.current = false)
          }
        })
        .from(footer, { y: () => window.innerHeight * 0.5, ease: "none" }, 0)
        .fromTo(params, { cell: 1 }, { cell: 0.73, ease: "none" }, 0);
    },
    { scope: ref }
  );

  return (
    <footer ref={ref} className="footer js-footer">
      <div className="footer__wrap">
        <div className="footer__main">
          <div className="footer__marquee">
            <Marquee>
              <span className="footer__marquee-text">{FOOTER.marquee}</span>
              <span className="footer__marquee-icon">
                <PixelIcon name="arrowLarge" />
              </span>
              <span className="footer__marquee-text">{FOOTER.marquee}</span>
              <span className="footer__marquee-icon">
                <PixelIcon name="arrowLarge" />
              </span>
            </Marquee>
          </div>

          <div className="footer__infos">
            <div className="footer__info-group">
              <p className="footer__info-label">{FOOTER.infosTitle}</p>
              <div className="footer__info-links">
                {FOOTER.links.map((link) => (
                  <SmartLink key={link.href} className="footer__info-link" href={link.href}>
                    {link.label}
                  </SmartLink>
                ))}
              </div>
            </div>
            <nav className="footer__nav" aria-label="Footer">
              <ul>
                {NAVIGATION.map((item, index) => (
                  <li key={item.id} className="footer__nav-item">
                    <SmartLink className="footer__nav-link" href={item.href}>
                      <span className="footer__nav-link-bg" aria-hidden="true" />
                      <span className="t-xl footer__nav-link-index">{String(index + 1).padStart(2, "0")}</span>
                      <span className="t-xl footer__nav-link-label">{item.label}</span>
                      <span className="footer__nav-link-icon" aria-hidden="true">
                        <span className="footer__nav-link-icon-inner">
                          <PixelIcon name="arrowLarge" />
                        </span>
                      </span>
                    </SmartLink>
                  </li>
                ))}
              </ul>
            </nav>
          </div>

          <div className="footer__end">
            <div className="footer__end-wrapper">
              <ul className="footer__end-links">
                <li>© {new Date().getFullYear()} Saga</li>
                {FOOTER.legal.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <p className="footer__credits">
                <span>{FOOTER.credits}</span>
              </p>
            </div>
          </div>
        </div>
      </div>
      <div ref={canvasRef} className="footer__canvas" aria-hidden="true" />
    </footer>
  );
}

/** Four copies scrolling half their width forever; the halves are identical, so it never seams. */
function Marquee({ children }: { children: React.ReactNode }) {
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    if (prefersReducedMotion()) {
      wrap.style.animation = "none";
      return;
    }
    // A constant 100px a second, whatever the viewport makes the text's width.
    const observer = new ResizeObserver(() => wrap.style.setProperty("--marquee-duration", `${wrap.scrollWidth / 200}s`));
    observer.observe(wrap);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="marquee">
      <div ref={wrapRef} className="marquee__wrap">
        {[0, 1, 2, 3].map((copy) => (
          <div key={copy} className="marquee__item" aria-hidden={copy > 0 ? true : undefined}>
            {children}
          </div>
        ))}
      </div>
    </div>
  );
}
