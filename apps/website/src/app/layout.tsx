import type { Metadata, Viewport } from "next";
import { Azeret_Mono, Inter_Tight } from "next/font/google";
import { Loader } from "@/components/chrome/loader";
import { Noise } from "@/components/chrome/noise";
import { PageStateProvider } from "@/components/providers/page-state";
import { SmoothScroll } from "@/components/providers/smooth-scroll";
import "./globals.css";

// Fed into --font-sans / --font-mono by src/styles/base.css, which reads these variables
// rather than naming the families itself (and tightens Inter Tight's tracking to suit).
const display = Inter_Tight({ subsets: ["latin"], variable: "--font-display-src", display: "swap" });
const mono = Azeret_Mono({ subsets: ["latin"], weight: ["700"], variable: "--font-mono-src", display: "swap" });

export const metadata: Metadata = {
  title: "Saga — cited answers over your own sources",
  description:
    "Saga turns your PDFs and links into a private, source-cited knowledge base you can chat with."
};

export const viewport: Viewport = {
  themeColor: "#0e0f12",
  colorScheme: "dark"
};

// The page is the product's dark theme; sections that need its light theme opt in with `.light`.
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`dark ${display.variable} ${mono.variable}`}>
      <body>
        <PageStateProvider>
          <SmoothScroll>
            <div className="page__wrap">
              <div className="page__container">
                <Loader />
                <div className="transition__container">
                  <div className="transition__node">
                    <Noise />
                    {children}
                  </div>
                </div>
              </div>
            </div>
          </SmoothScroll>
        </PageStateProvider>
      </body>
    </html>
  );
}
