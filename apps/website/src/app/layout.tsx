import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

// Aeonik/Input are licensed; Inter + JetBrains Mono are the Google-hosted substitutes wired
// onto the --font-sans / --font-mono variables the Saga tokens read.
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Saga — cited answers over your own sources",
  description:
    "Saga turns your PDFs and links into a private, source-cited knowledge base you can chat with."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
