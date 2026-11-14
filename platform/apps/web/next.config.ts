import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// NEXORA Core, reached server-side. The browser only ever talks to the portal's own origin:
// /v1/* is proxied, so the session cookie stays first-party (__Host-, SameSite=Lax).
const CORE = process.env.NEXORA_API_URL ?? "http://localhost:8080";

const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'; object-src 'none'; base-uri 'self'" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "camera=(), geolocation=(), payment=()" },
];

const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/v1/:path*", destination: `${CORE}/v1/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default createNextIntlPlugin("./src/i18n/request.ts")(config);
