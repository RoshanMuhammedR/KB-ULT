"use client";

import { useEffect, useRef, useState, type MouseEvent } from "react";
import { gsap, ScrollTrigger, useGSAP } from "@/lib/gsap";
import { ACCOUNT, NAVIGATION } from "@/lib/content";
import { useLenis } from "@/components/providers/smooth-scroll";
import { PixelIcon } from "@/components/ui/pixel-icon";
import { SagaMark } from "@/components/ui/saga-mark";
import { leave, SmartLink } from "@/components/ui/smart-link";

const REVEAL_EASE = "power4.inOut";

/**
 * The fixed top bar and the menu card it opens.
 *
 * The bar slips away while scrolling down and returns on the way back up; over a light
 * section it inverts. The spark in the corner folds and turns while hovered.
 */
export function Navbar() {
  const navRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLElement>(null);
  const menuTimeline = useRef<gsap.core.Timeline | null>(null);
  const logoTimeline = useRef<gsap.core.Timeline | null>(null);
  const logoIdle = useRef(true);
  const openRef = useRef(false);
  const hiddenRef = useRef(false);
  const [open, setOpen] = useState(false);
  const lenis = useLenis();

  const { contextSafe } = useGSAP(() => {
    const nav = navRef.current;
    const menu = menuRef.current;
    if (!nav || !menu) return;

    const svg = nav.querySelector(".js-logo-nav svg");
    const petals = nav.querySelectorAll(".js-logo-nav .js-petal");
    gsap.set(petals, { transformOrigin: "50% 50%" });
    logoTimeline.current = gsap
      .timeline({ paused: true, repeat: -1 })
      .to(petals, { scale: 0, stagger: { amount: 0.05 }, duration: 0.5, ease: "power2.inOut" }, 0)
      .to(petals, { scale: 1, stagger: { amount: 0.05 }, duration: 0.5, ease: "power2.inOut" }, 0.5)
      .to(svg, { rotation: 180, transformOrigin: "50% 50%", duration: 1, ease: "power2.inOut" }, 0);

    menuTimeline.current = gsap
      .timeline({ paused: true })
      .fromTo(menu, { opacity: 0, pointerEvents: "none" }, { opacity: 1, pointerEvents: "auto", duration: 0.05 })
      .fromTo(menu.querySelector(".js-navmenu-bg"), { scale: 0 }, { scale: 1, duration: 0.8, ease: REVEAL_EASE })
      .fromTo(
        menu.querySelectorAll(".js-navmenu-value"),
        { yPercent: 105 },
        { yPercent: 0, duration: 0.8, ease: REVEAL_EASE, stagger: { amount: 0.05, from: "end" } },
        "-=0.55"
      )
      .fromTo(
        menu.querySelectorAll(".js-navmenu-link"),
        { yPercent: 105 },
        { yPercent: 0, duration: 0.8, ease: REVEAL_EASE, stagger: { amount: 0.05, from: "end" } },
        "-=0.75"
      );

    // Over a light section the bar takes the light theme itself, so its ink inverts with it.
    // Refreshed after the sections' pins, whose spacing moves these positions.
    document.querySelectorAll<HTMLElement>("[data-surface='light']").forEach((section) => {
      ScrollTrigger.create({
        trigger: section,
        start: "top top+=80",
        end: "bottom top+=80",
        refreshPriority: -1,
        toggleClass: { targets: nav, className: "light" }
      });
    });
  });

  const onLogoEnter = contextSafe(() => {
    if (!logoTimeline.current || !logoIdle.current) return;
    logoIdle.current = false;
    logoTimeline.current.play();
  });

  // Let the current turn finish rather than snapping back mid-fold.
  const onLogoLeave = contextSafe(() => {
    const timeline = logoTimeline.current;
    const link = navRef.current?.querySelector(".js-logo-nav");
    if (!timeline || !link || logoIdle.current) return;
    timeline.pause();
    link.classList.add("is-exiting-hover");
    gsap.to(timeline, {
      time: timeline.duration(),
      duration: (1 - timeline.progress()) * timeline.duration(),
      ease: "none",
      onComplete: () => {
        link.classList.remove("is-exiting-hover");
        timeline.progress(0).pause();
        logoIdle.current = true;
      }
    });
  });

  const onLogoClick = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    setOpen(false);
    if (window.location.pathname === "/") lenis?.scrollTo(0, { duration: 1.2 });
    else leave("/");
  };

  useEffect(() => {
    openRef.current = open;
    const timeline = menuTimeline.current;
    if (!timeline) return;
    if (open) {
      timeline.play();
      document.body.classList.add("is-menu-open");
      hiddenRef.current = false;
      gsap.to(navRef.current, { y: 0, duration: 0.4, ease: "power3.out", overwrite: true });
    } else {
      timeline.reverse();
      document.body.classList.remove("is-menu-open");
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // Slip away while scrolling down, come back on the way up.
  useEffect(() => {
    if (!lenis) return;
    let last = lenis.scroll;
    const onTick = () => {
      const nav = navRef.current;
      if (!nav) return;
      const scroll = lenis.scroll;
      const direction = Math.sign(scroll - last);
      last = scroll;
      if (openRef.current) return;
      if (scroll < 80) {
        if (hiddenRef.current) {
          hiddenRef.current = false;
          gsap.to(nav, { y: 0, duration: 0.4, ease: "power3.out", overwrite: true });
        }
        return;
      }
      if (direction === 1 && !hiddenRef.current) {
        hiddenRef.current = true;
        const offset = nav.offsetHeight + nav.getBoundingClientRect().top + 8;
        gsap.to(nav, { y: -offset, duration: 0.4, ease: "power3.in", overwrite: true });
      } else if (direction === -1 && hiddenRef.current) {
        hiddenRef.current = false;
        gsap.to(nav, { y: 0, duration: 0.4, ease: "power3.out", overwrite: true });
      }
    };
    gsap.ticker.add(onTick);
    return () => gsap.ticker.remove(onTick);
  }, [lenis]);

  const close = () => setOpen(false);

  return (
    <>
      <nav className="navbar" ref={navRef}>
        <div className="navbar__container">
          <a
            href="/"
            className="navbar__link js-logo-nav"
            aria-label="Saga, back to the top"
            onMouseEnter={onLogoEnter}
            onMouseLeave={onLogoLeave}
            onClick={onLogoClick}
          >
            <SagaMark />
          </a>
          <div className="navbar__actions">
            <div className="navbar__account">
              <SmartLink className="navbar__account-item" href={ACCOUNT.login.href}>
                {ACCOUNT.login.label}
              </SmartLink>
              <SmartLink className="navbar__account-item navbar__account-item--accent" href={ACCOUNT.register.href}>
                {ACCOUNT.register.label}
              </SmartLink>
            </div>
            <button
              type="button"
              className="navbar__toggle"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-controls="navmenu"
              aria-expanded={open}
              onClick={(event) => {
                setOpen((value) => !value);
                event.currentTarget.blur();
              }}
            >
              <span className="navbar__toggle-label">Menu</span>
              <span className="navbar__toggle-button">
                <span className="navbar__toggle-button-open" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
                <span className="navbar__toggle-button-close" aria-hidden="true">
                  <span />
                  <span />
                </span>
              </span>
            </button>
          </div>
        </div>
      </nav>

      <button type="button" className="navmenu__close" onClick={close} tabIndex={-1}>
        <span className="sr-only">Close menu</span>
      </button>

      <nav className="navmenu light" ref={menuRef} id="navmenu" aria-label="Main menu" inert={!open}>
        <div className="navmenu__bg js-navmenu-bg" />
        <ul className="navmenu__list">
          {NAVIGATION.map((item, index) => (
            <li key={item.id} className="navmenu__item">
              <SmartLink className="navmenu__link js-navmenu-link" href={item.href} onClick={close}>
                <span className="navmenu__link-bg" aria-hidden="true" />
                <span className="t-xl navmenu__link-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="t-xl navmenu__link-label">{item.label}</span>
                <span className="navmenu__link-icon" aria-hidden="true">
                  <span className="navmenu__link-icon-inner">
                    <PixelIcon name="arrowLarge" />
                  </span>
                </span>
              </SmartLink>
            </li>
          ))}
        </ul>
        <div className="navmenu__infos">
          {ACCOUNT.groups.map((group) => (
            <div key={group.title} className="navmenu__info-group">
              <div className="navmenu__info-cell-item">
                <p className="navmenu__info-title js-navmenu-value">{group.title}</p>
              </div>
              <div className="navmenu__info-cell-item">
                <SmartLink className="navmenu__info-value js-navmenu-value" href={group.href} onClick={close}>
                  {group.label}
                </SmartLink>
              </div>
            </div>
          ))}
        </div>
      </nav>
    </>
  );
}
