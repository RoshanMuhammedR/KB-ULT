import { Footer } from "@/components/chrome/footer";
import { NavSpy } from "@/components/chrome/nav-spy";
import { Navbar } from "@/components/chrome/navbar";
import { About } from "@/components/sections/about";
import { GetStarted } from "@/components/sections/get-started";
import { Hero } from "@/components/sections/hero";
import { HowItWorks } from "@/components/sections/how-it-works";
import { Library } from "@/components/sections/library";
import { Privacy } from "@/components/sections/privacy";

/**
 * One page, in order. The hero is pinned behind everything; `page__content` scrolls up over
 * it and, a screen before its end, off the footer that has been waiting underneath.
 * Sections create their scroll triggers in this order, which is the order they must be
 * measured in - so keep new sections in reading order here.
 */
export default function LandingPage() {
  return (
    <>
      <Navbar />
      <Hero />
      <main className="page__content js-page-content">
        <About />
        <div className="page__home-sections">
          <HowItWorks />
          <Library />
        </div>
        <Privacy />
        <GetStarted />
      </main>
      <NavSpy />
      <Footer />
    </>
  );
}
