import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // @kb/ui and @kb/shared ship raw TS/TSX, so Next must transpile them.
  transpilePackages: ["@kb/ui", "@kb/shared"],
  // The product app is served under /app so it can share one origin with the marketing
  // site, whose rewrites route /app/* here (see apps/website/next.config.ts).
  basePath: "/app"
};

export default nextConfig;
