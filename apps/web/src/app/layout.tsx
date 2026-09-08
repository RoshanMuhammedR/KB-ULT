import type { Metadata } from "next";
import { JetBrains_Mono, Newsreader, Plus_Jakarta_Sans } from "next/font/google";
import { THEME_SCRIPT } from "@kb/ui";
import "./globals.css";
import { StoreBootstrap } from "@/components/saga/store-bootstrap";
import { Toaster } from "@/components/saga/toaster";

// Fed into --font-sans / --font-serif / --font-mono by packages/ui/src/theme.css, which
// reads these variables rather than naming the families itself.
const sans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans-src",
  display: "swap"
});
// Answer prose and display headings only. Loaded here rather than in a component because
// next/font has to hoist to a module scope it can statically see.
const serif = Newsreader({ subsets: ["latin"], variable: "--font-serif-src", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-src", display: "swap" });

export const metadata: Metadata = {
  title: "Saga — cited answers over your sources",
  description: "Upload documents and links, then chat with source-cited answers."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        {/* Applies the stored theme before first paint, so a dark reload never flashes light. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        {/* Hydrates the stores from the session cookie, in an effect — never during render. */}
        <StoreBootstrap />
        {children}
        <Toaster />
      </body>
    </html>
  );
}
