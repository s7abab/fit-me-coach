const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // The browser talks to /api/*, Next forwards it to FastAPI: no CORS, works on any port
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
  // /ask waits on the agent, which can take longer than the 30s default
  experimental: { proxyTimeout: 120_000 },
};

export default nextConfig;
