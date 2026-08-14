import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // @kb/ui and @kb/shared ship raw TS/TSX, so Next must transpile them.
  transpilePackages: ["@kb/ui", "@kb/shared"],
  // Self-contained server bundle for the production image (see apps/website/Dockerfile).
  output: "standalone"
};

export default nextConfig;
