import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",          // Static export — no server needed, works on Cloudflare Pages
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,       // Required for static export (no Next.js image optimizer)
    remotePatterns: [
      { protocol: "http",  hostname: "localhost" },
      { protocol: "http",  hostname: "backend" },
      { protocol: "https", hostname: "*.ngrok-free.app" },
      { protocol: "https", hostname: "*.ngrok-free.dev" },
    ],
  },
  // Bake the production API URL at build time for static export.
  // Cloudflare Pages dashboard env var takes precedence if set.
  // Change this when the backend moves to a permanent domain.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "https://lunacy-unsettled-probe.ngrok-free.dev",
  },
};

export default nextConfig;
