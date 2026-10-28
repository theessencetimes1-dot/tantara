import type { NextConfig } from 'next';
const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  env: {
    NEXT_PUBLIC_WORKSPACE_TIME_ZONE: process.env.TANTARA_WORKSPACE_TIME_ZONE ?? 'Asia/Kolkata',
  },
  async rewrites() {
    const origin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
    return [
      { source: '/api/v1/ingest/file', destination: `${origin}/ingest/file` },
      { source: '/api/v1/:path*', destination: `${origin}/api/v1/:path*` },
      { source: '/health', destination: `${origin}/health` },
    ];
  },
};
export default nextConfig;
