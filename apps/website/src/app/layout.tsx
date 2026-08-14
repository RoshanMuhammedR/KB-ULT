import type { Metadata } from "next";
import { Inter_Tight, JetBrains_Mono } from "next/font/google";
import { THEME_SCRIPT } from "@kb/ui";
import "./globals.css";

// Fed into --font-sans / --font-mono by packages/ui/src/theme.css, which reads these
// variables rather than naming the families itself.
const sans = Inter_Tight({ subsets: ["latin"], variable: "--font-sans-src", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-src", display: "swap" });

export const metadata: Metadata = {
  title: "Saga — cited answers over your own sources",
  description:
    "Saga turns your PDFs and links into a private, source-cited knowledge base you can chat with."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        {/* Applies the stored theme before first paint, so a dark reload never flashes light. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
