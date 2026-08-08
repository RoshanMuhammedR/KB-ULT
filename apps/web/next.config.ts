import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // @kb/ui ships raw TSX, so Next must transpile it.
  transpilePackages: ["@kb/ui"],
  // The product app is served under /app so it can share one origin (and one published
  // port) with the marketing site — Caddy routes /app/* here and /* to the website.
  basePath: "/app",
  // Self-contained server bundle for the production image (see apps/web/Dockerfile).
  output: "standalone"
};

export default nextConfig;
