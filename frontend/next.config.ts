import type { NextConfig } from "next";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  serverExternalPackages: [],
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    remotePatterns: [
      { protocol: "http",  hostname: "localhost" },
      { protocol: "http",  hostname: "backend" },
      { protocol: "https", hostname: "*.ngrok-free.app" },
      { protocol: "https", hostname: "*.ngrok-free.dev" },
    ],
  },
  // Proxy /api/proxy-media/* → backend /media/* so frontend can load images
  // without CORS issues and without hard-coding the backend URL in HTML.
  async rewrites() {
    return [
      {
        source: "/api/proxy-media/:path*",
        destination: `${API_BASE}/media/:path*`,
      },
    ];
  },
};

export default nextConfig;
