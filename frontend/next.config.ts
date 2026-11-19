import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image (docs/DEPLOYMENT_ARCHITECTURE.md §1).
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // Development only: mirror Nginx (ADR-006) so browser code can call same-origin `/api/*`.
  // Production builds contain no rewrite; Nginx routes `/api/` to FastAPI.
  // Account pages: never framed (clickjacking) and never leak URLs via Referer.
  async headers() {
    const accountPages = [
      "/sign-in",
      "/register",
      "/forgot-password",
      "/reset-password",
      "/verify-email",
      "/account/:path*",
    ];
    return accountPages.map((source) => ({
      source,
      headers: [
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "Cache-Control", value: "no-store" },
      ],
    }));
  },
  async rewrites() {
    if (!isDev) return [];
    const backend = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
