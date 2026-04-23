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
};

export default nextConfig;
