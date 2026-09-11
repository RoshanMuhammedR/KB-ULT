"use client";

import { useEffect, type RefObject } from "react";
import { Color, SRGBColorSpace, WebGLRenderer } from "three";
import { gsap } from "@/lib/gsap";

export type SceneHandle = {
  resize(width: number, height: number, pixelRatio: number): void;
  frame(time: number, delta: number): void;
  dispose(): void;
};

type Options = {
  maxPixelRatio?: number;
  /** Checked every frame; lets a section park its scene without unmounting it. */
  isActive?: () => boolean;
};

/**
 * Mount a renderer into `container` and run the scene `create` builds - but only while it
 * can be seen. Off-screen, the frame callback is detached from gsap's ticker entirely, so a
 * scene costs nothing until it scrolls back into view. Frames ride gsap's ticker rather than
 * their own requestAnimationFrame so they land on the same frame as the scroll that drives them.
 */
export function useThreeScene(
  containerRef: RefObject<HTMLElement | null>,
  create: (renderer: WebGLRenderer, container: HTMLElement) => SceneHandle,
  { maxPixelRatio = 1.75, isActive }: Options = {}
) {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance", stencil: false });
    } catch {
      return; // No WebGL: every section still reads without its scene.
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, maxPixelRatio));
    container.appendChild(renderer.domElement);
    const scene = create(renderer, container);

    let elapsed = 0;
    let running = false;
    const tick = (_time: number, deltaMs: number) => {
      if (isActive && !isActive()) return;
      const delta = Math.min(deltaMs / 1000, 0.1);
      elapsed += delta;
      scene.frame(elapsed, delta);
    };
    const setRunning = (value: boolean) => {
      if (value === running) return;
      running = value;
      if (value) gsap.ticker.add(tick);
      else gsap.ticker.remove(tick);
    };

    const resize = () => {
      const { clientWidth: width, clientHeight: height } = container;
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      scene.resize(width, height, renderer.getPixelRatio());
      scene.frame(elapsed, 0);
    };
    const sizeObserver = new ResizeObserver(resize);
    sizeObserver.observe(container);
    const viewObserver = new IntersectionObserver(([entry]) => setRunning(entry.isIntersecting), {
      rootMargin: "64px"
    });
    viewObserver.observe(container);

    return () => {
      setRunning(false);
      sizeObserver.disconnect();
      viewObserver.disconnect();
      scene.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
    // The scene is built once per mount; `create` and the options are read at that moment.
  }, [containerRef]); // eslint-disable-line react-hooks/exhaustive-deps
}

/** sRGB bytes as a three colour, converted into the renderer's linear working space. */
export function toColor([r, g, b]: [number, number, number]) {
  return new Color().setRGB(r / 255, g / 255, b / 255, SRGBColorSpace);
}
