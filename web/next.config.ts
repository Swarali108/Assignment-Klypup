import type { NextConfig } from "next";

// The browser only ever talks to this app: /api/* is rewritten to the data service, so the session
// cookie is same-origin. cacheComponents / partialPrefetching are intentionally OFF: every page reads
// live, per-request data, and classic dynamic rendering keeps dynamic routes simple.
// API_ORIGIN: where the data service lives (e.g. https://<service>.up.railway.app on Railway). Read at BUILD time
// for the rewrite, so changing it needs a redeploy. API_INTERNAL_ORIGIN is the older name, still honoured.
const API_ORIGIN = (process.env.API_ORIGIN || process.env.API_INTERNAL_ORIGIN || "http://127.0.0.1:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  devIndicators: false,
  // APP_ENV=production also reaches the browser bundle (it forces the chat preview mock off and hides sample files).
  env: { NEXT_PUBLIC_APP_ENV: process.env.NEXT_PUBLIC_APP_ENV || process.env.APP_ENV || "" },
  // Server-sent events (live processing) must not be buffered or cut at 30 s by the proxy.
  compress: false,
  experimental: { proxyTimeout: 600_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  // No sample files in production.
  async redirects() {
    return /^prod(uction)?$/i.test(process.env.NEXT_PUBLIC_APP_ENV || process.env.APP_ENV || "")
      ? [{ source: "/sample_book.csv", destination: "/today", permanent: false }]
      : [];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
