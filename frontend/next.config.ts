import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: [],
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
