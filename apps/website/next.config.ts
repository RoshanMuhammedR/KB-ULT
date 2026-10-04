import type { NextConfig } from "next";

// Production only (set on the Vercel project): this site owns the domain and does what a
// reverse proxy would, so the product app and the API share its origin. Unset in dev, where
// each app runs on its own port and these rewrites simply do not exist.
const WEB_ORIGIN = process.env.WEB_ORIGIN; // the product app's deployment, e.g. https://kb-web.vercel.app
const API_ORIGIN = process.env.API_ORIGIN; // the API, e.g. https://kb-api.onrender.com

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // @kb/ui and @kb/shared ship raw TS/TSX, so Next must transpile them.
  transpilePackages: ["@kb/ui", "@kb/shared"],
  async rewrites() {
    // `beforeFiles`: these paths belong to the other services outright, so nothing this app
    // serves may shadow them.
    return {
      beforeFiles: [
        // The product app keeps its own `basePath: "/app"`, so paths pass through unchanged
        // (Next.js multi-zones), its assets included.
        ...(WEB_ORIGIN
          ? [
              { source: "/app", destination: `${WEB_ORIGIN}/app` },
              { source: "/app/:path*", destination: `${WEB_ORIGIN}/app/:path*` }
            ]
          : []),
        // The API's routes have no /api prefix; the browser's same-origin /api/* is stripped here.
        ...(API_ORIGIN ? [{ source: "/api/:path*", destination: `${API_ORIGIN}/:path*` }] : [])
      ],
      afterFiles: [],
      fallback: []
    };
  }
};

export default nextConfig;
