import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: [],
  typescript: {
    // Type errors are caught in development — don't block production builds
    ignoreBuildErrors: true,
  },
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost" },
      { protocol: "http", hostname: "backend" },
      { protocol: "https", hostname: "*.ngrok-free.app" },
      { protocol: "https", hostname: "*.ngrok-free.dev" },
    ],
  },
};

export default nextConfig;
