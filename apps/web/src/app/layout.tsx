import type { Metadata } from "next";
import { Inter_Tight, JetBrains_Mono } from "next/font/google";
import { THEME_SCRIPT } from "@kb/ui";
import "./globals.css";
import { StoreBootstrap } from "@/components/saga/store-bootstrap";
import { Toaster } from "@/components/saga/toaster";

// Fed into --font-sans / --font-mono by packages/ui/src/theme.css, which reads these
// variables rather than naming the families itself.
const sans = Inter_Tight({ subsets: ["latin"], variable: "--font-sans-src", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-src", display: "swap" });

export const metadata: Metadata = {
  title: "Saga — cited answers over your sources",
  description: "Upload documents and links, then chat with source-cited answers."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
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
