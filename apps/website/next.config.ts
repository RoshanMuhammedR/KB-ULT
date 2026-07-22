import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // @kb/ui ships raw TSX, so Next must transpile it.
  transpilePackages: ["@kb/ui"],
  // Allow the mapped dev domains (see scripts/dev-domains.sh) as dev origins.
  allowedDevOrigins: ["localhost", "127.0.0.1", "saga.test", "acme.test", "admin.test"]
};

export default nextConfig;
