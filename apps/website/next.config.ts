import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // @kb/ui ships raw TSX, so Next must transpile it.
  transpilePackages: ["@kb/ui"],
  // Self-contained server bundle for the production image (see apps/website/Dockerfile).
  output: "standalone"
};

export default nextConfig;
