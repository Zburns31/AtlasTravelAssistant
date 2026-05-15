import type { NextConfig } from "next";

const API_ORIGIN = process.env.ATLAS_API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        // Proxy all API calls to the FastAPI backend in dev so the
        // frontend can use same-origin fetch (no CORS dance in prod
        // behind a reverse proxy either).
        source: "/api/:path*",
        destination: `${API_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
