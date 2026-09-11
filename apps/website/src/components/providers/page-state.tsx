"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

/**
 * Whether the page has been revealed yet.
 *
 * The loader owns the first seconds of every visit; nothing that animates *in* should start
 * underneath it, and scrolling stays locked until it has gone. Intro timelines wait for
 * `visible`, and the smooth scroller starts on it.
 */
type PageState = { visible: boolean; reveal: () => void };

const PageStateContext = createContext<PageState>({ visible: true, reveal: () => {} });

export function PageStateProvider({ children }: { children: React.ReactNode }) {
  const [visible, setVisible] = useState(false);
  const value = useMemo(() => ({ visible, reveal: () => setVisible(true) }), [visible]);

  // Leaving fades the page out (see `leave`); coming Back restores it from the bfcache still
  // faded, so undo that on the way in.
  useEffect(() => {
    const onShow = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      document.querySelector<HTMLElement>(".transition__container")?.style.removeProperty("opacity");
    };
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, []);
  return <PageStateContext.Provider value={value}>{children}</PageStateContext.Provider>;
}

export const usePageState = () => useContext(PageStateContext);
